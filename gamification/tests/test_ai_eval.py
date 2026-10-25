import csv
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command, CommandError
from django.test import TestCase

from gamification.management.commands.seed_proof_types import PROOF_TYPES
from gamification.models import ProofType
from gamification.ocr.providers.base import ProviderResult


class AiEvaluationCommandTests(TestCase):
    def setUp(self):
        call_command("seed_proof_types", verbosity=0)
        self.proof_type = ProofType.objects.create(
            code="EVAL_PHOTO",
            category=ProofType.Category.ENGAGEMENT,
            label_fr="Photo de test",
            action_type="PROOF_EVAL_PHOTO",
            cap_count=5,
            cap_period=ProofType.CapPeriod.MONTH,
            keyword_groups=[],
            min_groups=0,
            requires_date=False,
            photo_only=True,
        )

    def _write_samples(self, samples, labels, count):
        samples.mkdir()
        image = Path(__file__).resolve().parents[2] / "samples" / "fixture_not_document.png"
        data = image.read_bytes()
        (samples / "fixture.png").write_bytes(data)
        with labels.open("w", newline="", encoding="utf-8") as output:
            fieldnames = [
                "filename", "claimed_type", "true_type", "expected_decision",
                "true_date", "true_amount", "true_merchant", "notes",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            active_codes = list(
                ProofType.objects.filter(is_active=True)
                .order_by("code")
                .values_list("code", flat=True)
            )
            for index in range(count):
                writer.writerow({
                    "filename": "fixture.png",
                    "claimed_type": active_codes[index % len(active_codes)],
                    "true_type": "OTHER",
                    "expected_decision": "REJECTED",
                    "true_date": "",
                    "true_amount": "",
                    "true_merchant": "",
                    "notes": "synthetic non-document",
                })

    def test_requires_thirty_labeled_samples_before_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples, labels = root / "samples", root / "labels.csv"
            self._write_samples(samples, labels, 3)
            with mock.patch("gamification.management.commands.ai_eval.get_provider") as get_provider:
                with self.assertRaisesRegex(CommandError, "At least 30 labeled samples"):
                    call_command(
                        "ai_eval",
                        str(samples),
                        "--labels",
                        str(labels),
                        "--providers",
                        "gemini",
                    )
            get_provider.assert_not_called()

    def test_repository_dataset_covers_all_fourteen_proof_types(self):
        samples = Path(__file__).resolve().parents[2] / "samples"
        with (samples / "labels.csv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))

        covered_codes = {row["claimed_type"] for row in rows}
        expected_codes = {item["code"] for item in PROOF_TYPES}
        self.assertGreaterEqual(len(rows), 30)
        self.assertEqual(expected_codes - covered_codes, set())
        self.assertTrue(all((samples / row["filename"]).is_file() for row in rows))

    def test_requires_coverage_of_every_active_proof_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples, labels = root / "samples", root / "labels.csv"
            self._write_samples(samples, labels, 30)
            with labels.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            for row in rows:
                row["claimed_type"] = self.proof_type.code
            with labels.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            with mock.patch("gamification.management.commands.ai_eval.get_provider") as get_provider:
                with self.assertRaisesRegex(
                    CommandError,
                    "must cover every active proof type",
                ):
                    call_command(
                        "ai_eval",
                        str(samples),
                        "--labels",
                        str(labels),
                        "--providers",
                        "gemini",
                    )
            get_provider.assert_not_called()

    @mock.patch("gamification.management.commands.ai_eval.time.sleep")
    def test_writes_metrics_report_and_side_by_side_csv_with_mocked_provider(self, sleep):
        provider = mock.Mock()
        provider.extract.return_value = ProviderResult(
            provider="gemini",
            model="test-model",
            transcript="",
            mean_confidence=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples, labels, reports = root / "samples", root / "labels.csv", root / "reports"
            self._write_samples(samples, labels, 30)
            with mock.patch(
                "gamification.management.commands.ai_eval.get_provider",
                return_value=provider,
            ):
                call_command(
                    "ai_eval",
                    str(samples),
                    "--labels",
                    str(labels),
                    "--providers",
                    "gemini",
                    "--out",
                    str(reports),
                )

            report = next(reports.glob("ai_eval_*.md")).read_text(encoding="utf-8")
            comparison = next(reports.glob("ai_eval_*.csv")).read_text(encoding="utf-8")

        self.assertIn("Macro-F1", report)
        self.assertIn("Précision", report)
        self.assertIn("Latence moyenne", report)
        self.assertIn("gemini_decision", comparison.splitlines()[0])
        self.assertEqual(provider.extract.call_count, 30)
