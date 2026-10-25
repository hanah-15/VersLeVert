import csv
import json
import statistics
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from waste.ai.advice import fallback_advice, generate_advice, validate_grounding
from waste.ai.service import AIInvalidResponseError, AIUnavailableError


class Command(BaseCommand):
    help = "Évalue les conseils Gemini sur les profils synthétiques."

    def handle(self, *args, **options):
        profiles_path = Path(__file__).resolve().parents[2] / "ai" / "eval" / "profiles.json"
        output_path = profiles_path.with_name("advice_results.csv")
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        rows = []
        durations = []
        valid = grounded = fallback_count = 0
        for profile in profiles:
            name = profile["profil"]
            stats = {key: value for key, value in profile.items() if key != "profil"}
            started = time.perf_counter()
            source = "ai"
            try:
                advice = generate_advice(stats)
                valid += 1
                is_grounded, _ = validate_grounding(stats, advice)
                grounded += int(is_grounded)
                if not is_grounded:
                    advice = fallback_advice(stats)
                    source = "fallback"
                    fallback_count += 1
            except (AIInvalidResponseError, AIUnavailableError, OSError, TimeoutError, ValueError) as exc:
                self.stderr.write(f"{name}: {exc}")
                advice = fallback_advice(stats)
                source = "fallback"
                fallback_count += 1
                grounded += 1
            duration = time.perf_counter() - started
            durations.append(duration)
            rows.append({
                "profil": name,
                "réponse": json.dumps(advice, ensure_ascii=False),
                "ancré": validate_grounding(stats, advice)[0],
                "durée": f"{duration:.3f}",
                "note_pertinence": "",
            })
            time.sleep(2)

        with output_path.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=["profil", "réponse", "ancré", "durée", "note_pertinence"],
            )
            writer.writeheader()
            writer.writerows(rows)
        median = statistics.median(durations) if durations else 0
        maximum = max(durations) if durations else 0
        total = len(profiles) or 1
        self.stdout.write(f"Taux JSON valide : {valid / total:.1%}")
        self.stdout.write(f"Taux de réponses ancrées : {grounded / total:.1%}")
        self.stdout.write(f"Taux de repli : {fallback_count / total:.1%}")
        self.stdout.write(f"Durée médiane : {median:.3f} s")
        self.stdout.write(f"Durée maximale : {maximum:.3f} s")
        self.stdout.write(f"CSV : {output_path}")
