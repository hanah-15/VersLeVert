from time import perf_counter

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from places.ai import GeminiUnavailableError, generate_json
from places.guide import SearchIntent, SYSTEM_INSTRUCTION


class Command(BaseCommand):
    help = "Make one small Gemini request to verify the places module AI configuration."

    def handle(self, *args, **options):
        start = perf_counter()
        try:
            response = async_to_sync(generate_json)(
                "Un parc pour un pique-nique", system_instruction=SYSTEM_INSTRUCTION,
                schema=SearchIntent.model_json_schema(),
            )
            intent = SearchIntent.model_validate_json(response)
        except (GeminiUnavailableError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        elapsed = perf_counter() - start
        self.stdout.write(self.style.SUCCESS(
            f"Gemini connected: {settings.PLACES_GEMINI_MODEL} ({elapsed:.2f}s)"
        ))
        self.stdout.write("GEMINI_OK: " + intent.objective)
