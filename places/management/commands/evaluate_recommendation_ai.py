import asyncio
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from places.ai import GeminiUnavailableError
from places.recommendation_ai import prepare_recommendation


class Command(BaseCommand):
    help = "Measure category accuracy and claim-warning recall on synthetic drafts (real Gemini calls)."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", required=True, help="Explicit consent to consume Gemini quota.")
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        if not settings.GEMINI_API_KEY:
            raise CommandError("GEMINI_API_KEY is missing.")
        path = Path(__file__).resolve().parents[2] / "evaluation" / "recommendations.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        rows = asyncio.run(self.evaluate(cases))
        completed = [r for r in rows if "category" in r]
        latencies = sorted(r["elapsed_ms"] for r in completed)
        expected_issues = sum(len(row["expected_issues"]) for row in rows)
        found_issues = sum(len(set(row.get("issues", [])) & set(row["expected_issues"])) for row in rows)
        report = {
            "measured_at": datetime.now(timezone.utc).isoformat(), "mode": "live",
            "model": settings.PLACES_GEMINI_MODEL, "case_count": len(rows), "completed_count": len(completed),
            "category_accuracy": sum(r.get("category") == r["expected_category"] for r in rows) / len(rows),
            "expected_issue_recall": found_issues / expected_issues if expected_issues else None,
            "latency_median_ms": statistics.median(latencies) if latencies else None,
            "latency_p95_ms": latencies[math.ceil(len(latencies) * .95) - 1] if latencies else None,
            "rows": rows,
            "location_exact_matches": sum(row.get("location_exact", False) for row in rows),
            "location_case_count": sum("location_exact" in row for row in rows),
            "feedback_topics_found": sum(sum(row.get("topics_found", {}).values()) for row in rows),
            "feedback_topic_count": sum(len(row.get("topics_found", {})) for row in rows),
            "limitations": [
                "Small synthetic French/English sample; not a general accuracy estimate.",
                "Warnings identify claims needing evidence; they do not establish whether a claim is true or false.",
                "Rewrites require exact source quotes and pass limited claim checks; author review remains necessary and truth is not verified.",
                "Latency covers the provider and validation, without browser rendering or cache.",
                "Category accuracy counts provider failures as incorrect; warning recall counts only manually labelled issues.",
                "Feedback topics are checked by lexical markers on one synthetic review, not a general semantic-quality score.",
            ],
        }
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for key, value in report.items():
            if key not in {"rows", "limitations"}:
                self.stdout.write(f"{key}: {value}")

    async def evaluate(self, cases):
        rows = []
        for case in cases:
            row = {"id": case["id"], "expected_category": case["category"], "expected_issues": case["expected_issues"]}
            try:
                result = await prepare_recommendation(case["product_name"], case["description"], use_cache=False)
                row.update(
                    category=result["category"], product_name=result["product_name"], description=result["description"],
                    issues=[warning["issue"] for warning in result["warnings"]], elapsed_ms=result["elapsed_ms"],
                    exact_source_quotes=all(quote in case["description"] for quote in result["evidence_quotes"]),
                    missing_information=result["missing_information"],
                    purchase_location=result["purchase_location"],
                )
                if "expected_location" in case:
                    row["location_exact"] = result["purchase_location"] == case["expected_location"]
                row["topics_found"] = {key: bool(re.search(pattern, result["description"], re.I)) for key, pattern in case.get("expected_topics", {}).items()}
            except GeminiUnavailableError:
                row["error"] = "provider_unavailable_or_invalid"
            rows.append(row)
            self.stdout.write(f"{row['id']}: {row.get('category', row.get('error'))}, {row.get('elapsed_ms', '-')}ms")
            self.stdout.flush()
        return rows
