from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .ai import generate_text


@override_settings(
    GEMINI_API_KEY="test-key",
    GEMINI_MODEL="shared-model",
    GEMINI_TIMEOUT_SECONDS=60,
)
class EventProviderSettingsTests(SimpleTestCase):
    def call_provider(self, client_class):
        client = client_class.return_value.__enter__.return_value
        client.interactions.create.return_value.output_text = "Une proposition écologique."
        self.assertEqual(generate_text("Préparer une collecte"), "Une proposition écologique.")
        return client.interactions.create.call_args.kwargs

    @override_settings(EVENTS_GEMINI_MODEL="events-model", EVENTS_GEMINI_TIMEOUT_SECONDS=20)
    @patch("events.ai.genai.Client")
    def test_events_keep_their_model_and_timeout_when_shared_settings_change(self, client_class):
        kwargs = self.call_provider(client_class)
        self.assertEqual(kwargs["model"], "events-model")
        self.assertEqual(kwargs["timeout"], 20)

    @override_settings(EVENTS_GEMINI_MODEL="", EVENTS_GEMINI_TIMEOUT_SECONDS=0)
    @patch("events.ai.genai.Client")
    def test_existing_shared_settings_remain_a_fallback(self, client_class):
        kwargs = self.call_provider(client_class)
        self.assertEqual(kwargs["model"], "shared-model")
        self.assertEqual(kwargs["timeout"], 60)
