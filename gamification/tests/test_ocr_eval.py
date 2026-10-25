import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from gamification.models import ProofType


class OcrEvalCommandTests(TestCase):
    def setUp(self):
        self.proof_type = ProofType.objects.create(
            code="EVAL_TEST",
            category=ProofType.Category.ENERGY,
            label_fr="Facture de test",
            action_type="PROOF_EVAL_TEST",
            cap_count=5,
            cap_period=ProofType.CapPeriod.MONTH,
            keyword_groups=[{"terms": ["facture"], "required": True}],
            min_groups=1,
            requires_date=False,
            always_review=True,
        )

    @override_settings(PROOF_MIN_SHORT_SIDE_PX=700, PROOF_BLUR_MIN_LAPLACIAN_VAR=60)
    @mock.patch(
        "gamification.management.commands.ocr_eval.compute_quality_metrics",
        return_value=SimpleNamespace(
            to_dict=lambda: {"blur": 150, "short_side": 1200, "brightness": 145}
        ),
    )
    @mock.patch(
        "gamification.management.commands.ocr_eval.read_document",
        return_value=SimpleNamespace(text="Facture test", mean_conf=0.95),
    )
    def test_reports_decision_accuracy_against_labels(self, read_document, quality):
        from io import StringIO

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = root / "samples"
            samples.mkdir()
            (samples / "sample.jpg").write_bytes(b"synthetic test image")
            labels = root / "labels.csv"
            with labels.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=["filename", "proof_type", "expected"])
                writer.writeheader()
                writer.writerow({
                    "filename": "sample.jpg",
                    "proof_type": self.proof_type.code,
                    "expected": "NEEDS_REVIEW",
                })

            stdout = StringIO()
            call_command("ocr_eval", str(samples), "--labels", str(labels), stdout=stdout)

        self.assertIn("EVAL_TEST | 1 | 0 | 1 | 0 | 0.950", stdout.getvalue())
        self.assertIn("Accuracy: 1/1 (100.0%)", stdout.getvalue())
        read_document.assert_called_once()
        quality.assert_called_once()

    def test_rejects_csv_sample_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = root / "samples"
            samples.mkdir()
            labels = root / "labels.csv"
            with labels.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=["filename", "proof_type", "expected"])
                writer.writeheader()
                writer.writerow({
                    "filename": "..\\outside.jpg",
                    "proof_type": self.proof_type.code,
                    "expected": "NEEDS_REVIEW",
                })

            with self.assertRaises(CommandError):
                call_command("ocr_eval", str(samples), "--labels", str(labels))
