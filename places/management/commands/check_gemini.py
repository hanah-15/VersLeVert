from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from places.ai import GeminiUnavailableError, generate_text


class Command(BaseCommand):
    help = "Make one small Gemini request to verify the places module AI configuration."

    def handle(self, *args, **options):
        start = perf_counter()
        try:
            response = generate_text("Reply with exactly GEMINI_OK.")
        except GeminiUnavailableError as exc:
            raise CommandError(str(exc)) from None
        elapsed = perf_counter() - start
        self.stdout.write(self.style.SUCCESS(
            f"Gemini connected: {settings.GEMINI_MODEL} ({elapsed:.2f}s)"
        ))
        self.stdout.write(response)
