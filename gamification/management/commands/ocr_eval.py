import csv
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from gamification.models import EcoProof, ProofType
from gamification.ocr.engine import read_document
from gamification.ocr.parsers import (
    check_keyword_requirements,
    extract_amounts,
    extract_dates,
    match_keyword_groups,
    pick_best_amount,
    pick_best_date,
)
from gamification.ocr.preprocess import compute_quality_metrics
from gamification.services.scoring import decision_from_score, score_proof
from gamification.services.rules import effective_window_days


class Command(BaseCommand):
    help = "Evaluate OCR, quality, and scoring decisions against a labeled CSV."

    def add_arguments(self, parser):
        parser.add_argument("samples", type=Path)
        parser.add_argument("--labels", type=Path, required=True)

    def handle(self, *args, **options):
        samples = options["samples"].resolve()
        labels_path = options["labels"]
        if not samples.is_dir():
            raise CommandError(f"Sample folder does not exist: {samples}")
        if not labels_path.is_file():
            raise CommandError(f"Labels CSV does not exist: {labels_path}")

        totals = defaultdict(lambda: {
            "count": 0,
            "confidence_sum": 0.0,
            "approved": 0,
            "rejected": 0,
        })
        confusion = Counter()
        mismatches = 0
        with labels_path.open(newline="", encoding="utf-8-sig") as labels_file:
            reader = csv.DictReader(labels_file)
            required_columns = {"filename", "proof_type", "expected"}
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                raise CommandError("Labels CSV must contain filename, proof_type, and expected columns.")

            for line_number, row in enumerate(reader, start=2):
                filename = row.get("filename", "").strip()
                proof_code = row.get("proof_type", "").strip()
                expected = row.get("expected", "").strip().upper()
                if expected not in {
                    EcoProof.Status.APPROVED,
                    EcoProof.Status.REJECTED,
                }:
                    raise CommandError(f"Invalid expected decision on CSV line {line_number}: {expected!r}")
                path = (samples / filename).resolve()
                if not filename or not path.is_relative_to(samples) or not path.is_file():
                    raise CommandError(f"Sample missing or filename invalid on CSV line {line_number}: {filename!r}")
                try:
                    proof_type = ProofType.objects.get(code=proof_code, is_active=True)
                except ProofType.DoesNotExist as exc:
                    raise CommandError(f"Unknown active proof type on CSV line {line_number}: {proof_code}") from exc
                image_bytes = path.read_bytes()
                result = read_document(image_bytes)
                metrics = compute_quality_metrics(image_bytes).to_dict()
                _, indices = match_keyword_groups(result.text, proof_type.keyword_groups or [])
                valid = check_keyword_requirements(
                    proof_type.keyword_groups or [], indices, proof_type.min_groups
                )
                document_date = pick_best_date(extract_dates(result.text), result.text)
                amount = pick_best_amount(extract_amounts(result.text), result.text)
                now = timezone.now().date()
                window_days = effective_window_days(proof_type)
                if (
                    metrics["short_side"] < max(1, settings.PROOF_MIN_SHORT_SIDE_PX // 2)
                    or metrics["blur"] < settings.PROOF_BLUR_MIN_LAPLACIAN_VAR / 4
                ):
                    decision = EcoProof.Status.REJECTED
                elif proof_type.requires_date and not document_date:
                    decision = EcoProof.Status.REJECTED
                elif document_date and document_date > now:
                    decision = EcoProof.Status.REJECTED
                elif (
                    document_date
                    and window_days is not None
                    and (now - document_date).days > window_days
                ):
                    decision = EcoProof.Status.REJECTED
                elif not valid:
                    decision = EcoProof.Status.REJECTED
                else:
                    score, _ = score_proof(
                        confidence=result.mean_conf,
                        matched_groups=len(indices),
                        total_groups=len(proof_type.keyword_groups or []),
                        requires_date=proof_type.requires_date,
                        has_valid_date=bool(document_date),
                        has_amount=amount is not None,
                        requires_amount=proof_type.requires_amount,
                        quality_metrics=metrics,
                        source=EcoProof.Source.UPLOAD,
                    )
                    flags = ["OCR_FAILED"] if not result.text.strip() else []
                    decision = decision_from_score(score, flags)

                key = proof_code
                totals[key]["count"] += 1
                totals[key]["confidence_sum"] += result.mean_conf
                totals[key][{
                    EcoProof.Status.APPROVED: "approved",
                    EcoProof.Status.REJECTED: "rejected",
                }[decision]] += 1
                confusion[(expected, decision)] += 1
                if expected and expected != decision:
                    mismatches += 1
                    self.stdout.write(f"{filename}: expected {expected}, got {decision}")

        self.stdout.write("Type | Samples | Approved | Rejected | Average OCR confidence")
        for proof_code, stats in sorted(totals.items()):
            average = stats["confidence_sum"] / stats["count"]
            self.stdout.write(
                f"{proof_code} | {stats['count']} | {stats['approved']} | "
                f"{stats['rejected']} | {average:.3f}"
            )
        total = sum(item["count"] for item in totals.values())
        correct = sum(count for (expected, actual), count in confusion.items() if expected == actual)
        self.stdout.write(f"Accuracy: {correct}/{total} ({correct / total:.1%})" if total else "Accuracy: n/a (no samples)")
        self.stdout.write(f"Mismatches: {mismatches}")
        self.stdout.write("Note: duplicate detection, user caps, and storage/anti-fraud history are not simulated.")
