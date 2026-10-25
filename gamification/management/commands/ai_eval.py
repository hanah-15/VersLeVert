"""Compare proof OCR providers against a labeled, privacy-safe sample set."""

import csv
import statistics
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.utils import timezone

from gamification.models import AiCallLog, EcoProof, ProofType
from gamification.ocr.parsers import (
    check_keyword_requirements,
    extract_amounts,
    extract_dates,
    extract_merchant,
    match_keyword_groups,
    pick_best_amount,
    pick_best_date,
)
from gamification.ocr.preprocess import compute_quality_metrics
from gamification.ocr.providers import get_provider
from gamification.ocr.providers.base import (
    ProviderBadResponse,
    ProviderError,
    ProviderQuotaExceeded,
    ProviderTimeout,
)
from gamification.services.pipeline import _cross_check
from gamification.services.rules import effective_window_days
from gamification.services.scoring import decision_from_score, score_proof

MINIMUM_SAMPLES = 30
REQUIRED_COLUMNS = {
    "filename",
    "claimed_type",
    "true_type",
    "expected_decision",
    "true_date",
    "true_amount",
    "true_merchant",
    "notes",
}
CLASSES = [
    EcoProof.Status.APPROVED,
    EcoProof.Status.REJECTED,
]


def _amount_matches(actual, expected):
    if actual is None or not expected:
        return False
    try:
        return abs(float(actual) - float(expected)) <= 0.001
    except (TypeError, ValueError):
        return False


def _percentile(values, quantile):
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _class_metrics(expected, predicted):
    matrix = {truth: {guess: 0 for guess in CLASSES} for truth in CLASSES}
    for truth, guess in zip(expected, predicted):
        matrix[truth][guess] += 1
    per_class = {}
    for label in CLASSES:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in CLASSES if other != label)
        fn = sum(matrix[label][other] for other in CLASSES if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
    accuracy = sum(matrix[label][label] for label in CLASSES) / max(1, len(expected))
    macro_f1 = sum(item["f1"] for item in per_class.values()) / len(CLASSES)
    return matrix, per_class, accuracy, macro_f1


def _decide(result, proof_type, image_bytes):
    metrics = compute_quality_metrics(image_bytes).to_dict()
    (
        document_date,
        amount,
        merchant,
        matched_count,
        matched_indices,
        keywords_valid,
        cross_check,
        flags,
    ) = _cross_check(result, proof_type)
    fields = result.fields or {}
    if fields.get("is_document_photo") is False and not proof_type.photo_only:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    if fields.get("readable") is False:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    if (
        metrics["short_side"] < max(1, settings.PROOF_MIN_SHORT_SIDE_PX // 2)
        or metrics["blur"] < settings.PROOF_BLUR_MIN_LAPLACIAN_VAR / 4
    ):
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    today = timezone.now().date()
    window_days = effective_window_days(proof_type)
    if proof_type.requires_date and not document_date:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    if document_date and document_date > today:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    if (
        document_date
        and window_days is not None
        and (today - document_date).days > window_days
    ):
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    if not keywords_valid:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags

    type_match = (
        float(bool(fields["matches_claimed_type"]))
        if "matches_claimed_type" in fields
        else float(bool(keywords_valid))
    )
    score, _ = score_proof(
        type_match=type_match,
        cross_check=cross_check,
        ai_self_conf=fields.get("self_confidence"),
        matched_groups=matched_count,
        total_groups=len(proof_type.keyword_groups or []),
        requires_date=proof_type.requires_date,
        has_valid_date=bool(document_date),
        has_amount=amount is not None,
        requires_amount=proof_type.requires_amount,
        quality_metrics=metrics,
        source=EcoProof.Source.UPLOAD,
    )
    if "TYPE_MISMATCH" in flags and not keywords_valid:
        return EcoProof.Status.REJECTED, (document_date, amount, merchant), flags
    return decision_from_score(score, flags), (document_date, amount, merchant), flags


class Command(BaseCommand):
    help = "Evaluate OCR providers against at least 30 privacy-safe labeled samples."

    def add_arguments(self, parser):
        parser.add_argument("samples", type=Path)
        parser.add_argument("--labels", type=Path, required=True)
        parser.add_argument(
            "--providers",
            default=",".join(settings.PROOF_OCR_PROVIDERS),
            help="Comma-separated provider names (gemini,ocrspace,tesseract).",
        )
        parser.add_argument("--out", type=Path, default=Path("reports"))

    def handle(self, *args, **options):
        samples = options["samples"].resolve()
        labels = options["labels"].resolve()
        if not samples.is_dir():
            raise CommandError(f"Sample directory does not exist: {samples}")
        if not labels.is_file():
            raise CommandError(f"Labels CSV does not exist: {labels}")
        providers = [name.strip().lower() for name in options["providers"].split(",") if name.strip()]
        if not providers or any(name not in {"gemini", "ocrspace", "tesseract"} for name in providers):
            raise CommandError("Choose one or more providers from gemini, ocrspace, tesseract.")

        with labels.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise CommandError(
                    "Labels CSV must contain: " + ", ".join(sorted(REQUIRED_COLUMNS))
                )
            rows = list(reader)
        if len(rows) < MINIMUM_SAMPLES:
            raise CommandError(
                f"At least {MINIMUM_SAMPLES} labeled samples are required; found {len(rows)}. "
                "Add synthetic or anonymized samples before running evaluation."
            )
        claimed_types = {row["claimed_type"].strip() for row in rows}
        active_types = set(
            ProofType.objects.filter(is_active=True).values_list("code", flat=True)
        )
        missing_types = sorted(active_types - claimed_types)
        if missing_types:
            raise CommandError(
                "Labeled samples must cover every active proof type; missing: "
                + ", ".join(missing_types)
            )

        external_calls = len(rows) * sum(name in {"gemini", "ocrspace"} for name in providers)
        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        used_calls = AiCallLog.objects.filter(created_at__gte=day_start).aggregate(
            total=Sum("request_count")
        )["total"] or 0
        remaining = max(0, settings.PROOF_AI_DAILY_BUDGET - used_calls)
        if external_calls > remaining:
            raise CommandError(
                f"Evaluation needs up to {external_calls} external provider calls, but only "
                f"{remaining} remain in today's configured budget. Reduce providers or wait."
            )

        samples_data = []
        for line, row in enumerate(rows, start=2):
            filename = row["filename"].strip()
            path = (samples / filename).resolve()
            if not filename or not path.is_relative_to(samples) or not path.is_file():
                raise CommandError(f"Invalid or missing sample on CSV line {line}: {filename!r}")
            expected = row["expected_decision"].strip().upper()
            if expected not in CLASSES:
                raise CommandError(f"Invalid expected_decision on CSV line {line}: {expected!r}")
            try:
                proof_type = ProofType.objects.get(code=row["claimed_type"].strip(), is_active=True)
            except ProofType.DoesNotExist as exc:
                raise CommandError(
                    f"Unknown active claimed_type on CSV line {line}: {row['claimed_type']!r}"
                ) from exc
            samples_data.append((row, path, proof_type, expected, path.read_bytes()))

        metrics_by_provider = {}
        csv_rows = [
            {"filename": path.name, "expected_decision": expected}
            for row, path, proof_type, expected, image_bytes in samples_data
        ]
        min_interval = 60 / max(1, settings.PROOF_AI_MAX_RPM)
        for provider_name in providers:
            provider = get_provider(provider_name)
            expected_all = []
            predicted_all = []
            latencies = []
            failures = timeouts = 0
            date_correct = date_total = 0
            amount_correct = amount_total = 0
            merchant_correct = merchant_total = 0
            type_correct = type_total = 0
            injection_approved = tampering_approved = 0
            last_call_finished = None
            for sample_index, (row, path, proof_type, expected, image_bytes) in enumerate(samples_data):
                if provider_name in {"gemini", "ocrspace"} and last_call_finished is not None:
                    wait = min_interval - (time.perf_counter() - last_call_finished)
                    if wait > 0:
                        time.sleep(wait)
                started = time.perf_counter()
                try:
                    result = provider.extract([image_bytes], proof_type)
                    status = AiCallLog.Status.OK
                    request_count = result.usage.get("requests", 1)
                    latency = int((time.perf_counter() - started) * 1000)
                    decision, extracted, flags = _decide(result, proof_type, image_bytes)
                except ProviderError as exc:
                    latency = int((time.perf_counter() - started) * 1000)
                    failures += 1
                    timeouts += isinstance(exc, ProviderTimeout)
                    status = (
                        AiCallLog.Status.TIMEOUT if isinstance(exc, ProviderTimeout)
                        else AiCallLog.Status.QUOTA if isinstance(exc, ProviderQuotaExceeded)
                        else AiCallLog.Status.BAD_RESPONSE if isinstance(exc, ProviderBadResponse)
                        else AiCallLog.Status.ERROR
                    )
                    request_count = getattr(exc, "request_count", 1)
                    decision = EcoProof.Status.REJECTED
                    extracted = (None, None, "")
                    result = None
                    flags = ["AI_UNAVAILABLE"]
                except Exception as exc:
                    latency = int((time.perf_counter() - started) * 1000)
                    failures += 1
                    status = AiCallLog.Status.ERROR
                    request_count = 1
                    decision = EcoProof.Status.REJECTED
                    extracted = (None, None, "")
                    result = None
                    flags = ["AI_UNAVAILABLE"]
                    self.stderr.write(
                        f"{provider_name}: sample processing error ({type(exc).__name__})"
                    )
                AiCallLog.objects.create(
                    provider=provider_name,
                    status=status,
                    latency_ms=max(0, latency),
                    request_count=request_count,
                )
                if provider_name in {"gemini", "ocrspace"}:
                    last_call_finished = time.perf_counter()
                latencies.append(latency)
                expected_all.append(expected)
                predicted_all.append(decision)
                true_date = row["true_date"].strip()
                true_amount = row["true_amount"].strip()
                true_merchant = row["true_merchant"].strip()
                actual_date, actual_amount, actual_merchant = extracted
                if true_date:
                    date_total += 1
                    date_correct += bool(actual_date and actual_date.isoformat() == true_date)
                if true_amount:
                    amount_total += 1
                    try:
                        amount_correct += _amount_matches(actual_amount, true_amount)
                    except (TypeError, ValueError):
                        pass
                if true_merchant:
                    merchant_total += 1
                    merchant_correct += SequenceMatcher(
                        None,
                        actual_merchant.casefold(),
                        true_merchant.casefold(),
                    ).ratio() >= 0.8
                if result and result.fields and result.fields.get("document_type"):
                    type_total += 1
                    type_correct += result.fields["document_type"] == row["true_type"].strip()
                notes = row["notes"].casefold()
                if any(token in notes for token in ("injection", "instruction", "approve this", "validez")):
                    injection_approved += decision == EcoProof.Status.APPROVED
                if any(token in notes for token in ("tamper", "edited", "modified", "retouche")):
                    tampering_approved += decision == EcoProof.Status.APPROVED
                csv_rows[sample_index].update({
                    f"{provider_name}_decision": decision,
                    f"{provider_name}_latency_ms": latency,
                    f"{provider_name}_date_match": bool(
                        true_date and actual_date and actual_date.isoformat() == true_date
                    ),
                    f"{provider_name}_amount_match": _amount_matches(actual_amount, true_amount),
                    f"{provider_name}_merchant_match": bool(
                        true_merchant
                        and SequenceMatcher(None, actual_merchant.casefold(), true_merchant.casefold()).ratio() >= 0.8
                    ),
                })
            matrix, per_class, accuracy, macro_f1 = _class_metrics(expected_all, predicted_all)
            metrics_by_provider[provider_name] = {
                "matrix": matrix,
                "per_class": per_class,
                "accuracy": accuracy,
                "macro_f1": macro_f1,
                "mean_latency": statistics.mean(latencies) if latencies else 0,
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "maximum": max(latencies, default=0),
                "failure_rate": failures / len(rows),
                "timeout_rate": timeouts / len(rows),
                "date_accuracy": date_correct / date_total if date_total else None,
                "amount_accuracy": amount_correct / amount_total if amount_total else None,
                "merchant_accuracy": merchant_correct / merchant_total if merchant_total else None,
                "type_accuracy": type_correct / type_total if type_total else None,
                "injection_approved": injection_approved,
                "tampering_approved": tampering_approved,
            }

        out_dir = options["out"].resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().date().isoformat()
        report_path = out_dir / f"ai_eval_{stamp}.md"
        csv_path = out_dir / f"ai_eval_{stamp}.csv"
        self._write_report(report_path, len(rows), metrics_by_provider)
        with csv_path.open("w", newline="", encoding="utf-8") as output:
            fieldnames = list(dict.fromkeys(key for row in csv_rows for key in row))
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        self.stdout.write(self.style.SUCCESS(f"Evaluation report: {report_path}"))
        self.stdout.write(self.style.SUCCESS(f"Comparison CSV: {csv_path}"))

    def _write_report(self, path, sample_count, results):
        lines = [
            f"# Évaluation des fournisseurs OCR — {timezone.now().date().isoformat()}",
            "",
            f"Échantillons évalués : {sample_count}.",
            "",
            "Les appels peuvent être facturés ou limités selon le fournisseur. Les contenus d'évaluation "
            "doivent être synthétiques ou anonymisés.",
            "",
        ]
        for provider, metrics in results.items():
            lines.extend([
                f"## {provider}",
                "",
                f"- Exactitude : {metrics['accuracy']:.3f}",
                f"- Macro-F1 : {metrics['macro_f1']:.3f}",
                f"- Latence moyenne / p50 / p95 / max : {metrics['mean_latency']:.0f} / "
                f"{metrics['p50']} / {metrics['p95']} / {metrics['maximum']} ms",
                f"- Taux d'échec / timeout : {metrics['failure_rate']:.1%} / "
                f"{metrics['timeout_rate']:.1%}",
                f"- Exactitude date / montant / partenaire / type : "
                f"{_display_metric(metrics['date_accuracy'])} / "
                f"{_display_metric(metrics['amount_accuracy'])} / "
                f"{_display_metric(metrics['merchant_accuracy'])} / "
                f"{_display_metric(metrics['type_accuracy'])}",
                f"- Documents injectés approuvés : {metrics['injection_approved']}",
                f"- Documents retouchés approuvés : {metrics['tampering_approved']}",
                "",
                "| Vérité \\ Prévision | Approuvée | Rejetée |",
                "|---|---:|---:|",
            ])
            for truth in CLASSES:
                row = metrics["matrix"][truth]
                lines.append(
                    f"| {truth} | {row[EcoProof.Status.APPROVED]} | "
                    f"{row[EcoProof.Status.REJECTED]} |"
                )
            lines.extend(["", "| Classe | Précision | Rappel | F1 |", "|---|---:|---:|---:|"])
            for label in CLASSES:
                stats = metrics["per_class"][label]
                lines.append(
                    f"| {label} | {stats['precision']:.3f} | {stats['recall']:.3f} | {stats['f1']:.3f} |"
                )
            lines.append("")
        if "tesseract" in results and "gemini" in results:
            delta = results["gemini"]["macro_f1"] - results["tesseract"]["macro_f1"]
            lines.extend([
                "## Comparaison automatique",
                "",
                f"Gemini a modifié le macro-F1 de {delta:+.3f} par rapport à Tesseract. "
                "Consultez les matrices de confusion ci-dessus pour localiser les erreurs restantes.",
                "",
            ])
        else:
            lines.extend([
                "## Comparaison automatique",
                "",
                "Le Tesseract de référence doit être inclus dans `--providers` pour calculer "
                "l'écart de macro-F1. Aucun résultat de référence n'est inventé.",
                "",
            ])
        path.write_text("\n".join(lines), encoding="utf-8")


def _display_metric(value):
    return f"{value:.3f}" if value is not None else "n/a"
