import asyncio
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from places.guide import SearchIntent, rank_catalogue, search_catalogue, tokens, INFORMATION_LABELS


DATA_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "cases.json"


def references(result):
    return [f"place:{item['id']}" for item in result["places"]] + [f"product:{item['id']}" for item in result["products"]]


def score(result, relevant):
    returned = references(result)
    expected = set(relevant)
    correct = len(set(returned) & expected)
    return {
        "precision": correct / len(returned) if returned else float(not expected),
        "recall": correct / len(expected) if expected else float(not returned),
        "reciprocal_rank": next((1 / (i + 1) for i, ref in enumerate(returned) if ref in expected), float(not returned and not expected)),
        "exact_set": set(returned) == expected,
    }


class Command(BaseCommand):
    help = "Evaluate the guide on a fictional labelled catalogue; --live explicitly calls Gemini."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="Use the real Gemini API (consumes quota).")
        parser.add_argument("--limit", type=int, default=12)
        parser.add_argument("--output", type=Path, help="Write the measured JSON report.")

    def handle(self, *args, **options):
        if options["live"] and not settings.GEMINI_API_KEY:
            raise CommandError("GEMINI_API_KEY is missing.")
        if not 1 <= options["limit"] <= 12:
            raise CommandError("--limit must be between 1 and 12.")
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        rows = asyncio.run(self.evaluate(data, options["live"], options["limit"]))
        latency = sorted(row["elapsed_ms"] for row in rows)
        report = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "mode": "live" if options["live"] else "offline_fallback",
            "model": settings.PLACES_GEMINI_MODEL, "case_count": len(rows),
            "ai_response_count": sum(row["source"] == "gemini" for row in rows),
            "macro_precision": statistics.mean(row["precision"] for row in rows),
            "macro_recall": statistics.mean(row["recall"] for row in rows),
            "mean_reciprocal_rank": statistics.mean(row["reciprocal_rank"] for row in rows),
            "exact_set_accuracy": statistics.mean(row["exact_set"] for row in rows),
            "literal_baseline_precision": statistics.mean(row["baseline"]["precision"] for row in rows),
            "literal_baseline_recall": statistics.mean(row["baseline"]["recall"] for row in rows),
            "latency_median_ms": statistics.median(latency),
            "latency_p95_ms": latency[math.ceil(len(latency) * .95) - 1],
            "valid_source_rate": statistics.mean(row["valid_sources"] for row in rows),
            "rows": rows,
            "limitations": [
                "Small synthetic, manually labelled set; not evidence of general real-world accuracy.",
                "Precision/recall are calculated on up to 3 places and 3 products; empty expected and returned sets score 1.",
                "Combined display order is places followed by products for reciprocal rank.",
                "Latency includes interpretation and fixture retrieval, not HTTP rendering or real database I/O; no cache.",
                "Fallback rows are explicitly labelled and are not successful AI responses.",
                "Source validity checks identifiers, not the truth of community descriptions or the interpretation of the query.",
            ],
        }
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for key in ("mode", "case_count", "ai_response_count", "macro_precision", "macro_recall", "exact_set_accuracy", "latency_median_ms", "latency_p95_ms", "valid_source_rate"):
            self.stdout.write(f"{key}: {report[key]}")

    async def evaluate(self, data, live, limit):
        from unittest.mock import patch

        rows = []
        valid = {f"place:{p['id']}" for p in data["catalogue"]["places"]} | {f"product:{p['id']}" for p in data["catalogue"]["products"]}
        for case in data["cases"][:limit]:
            request = {"query": case["query"], **case["filters"]}
            if live:
                result = await search_catalogue(request, snapshot=data["catalogue"], use_cache=False)
            else:
                with patch("places.guide.settings.GEMINI_API_KEY", ""):
                    result = await search_catalogue(request, snapshot=data["catalogue"], use_cache=False)
            literal = SearchIntent(
                objective=case["query"][:180], target="both", keywords=list(tokens(case["query"]))[:10],
                place_categories=[], product_categories=[], excluded_place_categories=[], location="", unavailable_information=[],
            )
            baseline = rank_catalogue(data["catalogue"], case["query"], literal, case["filters"])
            row = {
                "id": case["id"], "query": case["query"], "filters": case["filters"],
                "source": result["source"], "returned": references(result), "expected": case["relevant"],
                "objective": result["objective"], **score(result, case["relevant"]),
                "baseline": score(baseline, case["relevant"]), "elapsed_ms": result["elapsed_ms"],
                "valid_sources": set(references(result)) <= valid,
                "required_warning_present": not case.get("expected_warning") or INFORMATION_LABELS[case["expected_warning"]] in result["warnings"],
            }
            rows.append(row)
            self.stdout.write(f"{case['id']}: {row['source']}, precision={row['precision']:.2f}, recall={row['recall']:.2f}, {row['elapsed_ms']}ms")
            self.stdout.flush()
        return rows
