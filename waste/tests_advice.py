import hashlib
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .ai.advice import (
    build_stats,
    fallback_advice,
    get_or_create_advice,
    validate_grounding,
)
from .models import EcoAdvice, Status, WasteRequest, WasteType

User = get_user_model()


class AdviceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="advice-user", email="advice@example.com", password="pass"
        )
        self.other = User.objects.create_user(
            username="other-user", email="other@example.com", password="pass"
        )

    def make_request(self, user, **values):
        defaults = {
            "waste_type": WasteType.PLASTIC,
            "estimated_weight": Decimal("2.00"),
            "confirmed_weight": Decimal("1.50"),
            "co2_avoided": Decimal("0.750"),
            "address": "Ne doit pas apparaître",
            "latitude": 36.8,
            "longitude": 10.1,
            "status": Status.CONFIRMED,
            "confirmed_at": timezone.now(),
        }
        defaults.update(values)
        return WasteRequest.objects.create(user=user, **defaults)

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.advice.genai.Client")
    def test_grounded_response_is_saved(self, client_class):
        response = {
            "summary": "Vous avez trié 1.5 kg de déchets.",
            "tips": [
                {"title": "Continuer", "text": "Gardez vos habitudes."},
                {"title": "Plastique", "text": "Réduisez les emballages."},
                {"title": "Régularité", "text": "Triez régulièrement."},
            ],
        }
        client_class.return_value.models.generate_content.return_value.text = json.dumps(response)
        self.make_request(self.user)
        advice = get_or_create_advice(self.user)
        self.assertEqual(advice.source, "ai")
        self.assertTrue(advice.grounded)

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.advice.generate_advice")
    def test_invented_number_retries_then_falls_back(self, generate):
        invented = {
            "summary": "Vous avez trié 999 kg.",
            "tips": [
                {"title": "A", "text": "Continuez."},
                {"title": "B", "text": "Triez."},
                {"title": "C", "text": "Réduisez."},
            ],
        }
        generate.return_value = invented
        self.make_request(self.user)
        advice = get_or_create_advice(self.user)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(advice.source, "fallback")
        self.assertTrue(advice.grounded)

    @patch("waste.ai.advice.generate_advice", side_effect=OSError("network"))
    def test_api_failure_falls_back(self, generate):
        self.make_request(self.user)
        advice = get_or_create_advice(self.user)
        self.assertEqual(advice.source, "fallback")
        self.assertEqual(generate.call_count, 1)

    @patch("waste.ai.advice.generate_advice")
    def test_same_stats_hash_uses_cache(self, generate):
        generate.return_value = fallback_advice({
            "co2_total_kg": 0, "kg_sorted": 0, "collections_count": 0,
            "organic_kg": 0, "plastic_kg": 0, "kg_last_30_days": 0,
        })
        first = get_or_create_advice(self.user)
        second = get_or_create_advice(self.user)
        self.assertEqual(first.pk, second.pk)
        generate.assert_called_once()

    def test_build_stats_ignores_unconfirmed_and_personal_data(self):
        self.make_request(self.user)
        self.make_request(
            self.user,
            status=Status.REQUESTED,
            confirmed_weight=None,
            co2_avoided=None,
            confirmed_at=None,
        )
        stats = build_stats(self.user)
        self.assertEqual(stats["kg_sorted"], 1.5)
        self.assertEqual(stats["collections_count"], 1)
        self.assertNotIn("address", json.dumps(stats))
        self.assertNotIn("latitude", json.dumps(stats))
        self.assertNotIn("longitude", json.dumps(stats))

    def test_user_cannot_read_another_users_advice(self):
        advice = EcoAdvice.objects.create(
            user=self.other,
            payload=fallback_advice({
                "co2_total_kg": 0, "kg_sorted": 0, "collections_count": 0,
                "organic_kg": 0, "plastic_kg": 0, "kg_last_30_days": 0,
            }),
            stats_hash=hashlib.sha256(b"other").hexdigest(),
            source="fallback",
            grounded=True,
            duration_ms=1,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("waste:advice"))
        self.assertEqual(response.status_code, 404)

    def test_fallback_is_grounded_and_has_three_tips(self):
        stats = {
            "co2_total_kg": 0, "kg_sorted": 0, "collections_count": 0,
            "organic_kg": 0, "plastic_kg": 0, "kg_last_30_days": 0,
        }
        advice = fallback_advice(stats)
        self.assertEqual(len(advice["tips"]), 3)
        self.assertEqual(validate_grounding(stats, advice), (True, []))
