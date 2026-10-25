import json
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .ai import GeminiUnavailableError
from .models import ProductRecommendation
from .recommendation_ai import RecommendationPreparation, prepare_recommendation, verified_preparation


TEXT = "J'utilise une gourde inox depuis trois semaines. Je la remplis au lieu d'acheter des bouteilles jetables."


def preparation(**changes):
    return {
        "product_name": "gourde inox", "category": "home",
        "experience_quotes": ["J'utilise une gourde inox depuis trois semaines.", "Je la remplis au lieu d'acheter des bouteilles jetables."],
        "claims_to_check": [], "missing_information": [], **changes,
    }


class PreparationValidationTests(SimpleTestCase):
    def validate(self, description=TEXT, **changes):
        return verified_preparation(RecommendationPreparation.model_validate(preparation(**changes)), "", description)

    def test_generated_facts_and_names_cannot_enter_the_prepared_form(self):
        result = self.validate(product_name="Invented Brand", experience_quotes=["Certified organic and saves 100 kg of CO2."])
        self.assertEqual(result["product_name"], "")
        self.assertEqual(result["description"], "")
        self.assertIn("Précisez le nom du produit.", result["missing_information"])

    def test_prepared_description_contains_only_exact_source_spans_in_source_order(self):
        result = self.validate(experience_quotes=list(reversed(preparation()["experience_quotes"])))
        self.assertEqual(result["description"], "\n\n".join(preparation()["experience_quotes"]))
        self.assertEqual(result["product_name"], "gourde inox")
        unicode_source = "Ma Straße préférée. " + TEXT
        self.assertEqual(self.validate(description=unicode_source)["product_name"], "gourde inox")

    def test_unsupported_claim_is_flagged_and_removed_from_proposed_draft(self):
        source = TEXT + " Ce produit est 100% écologique et sans aucun impact."
        claim = "100% écologique"
        result = self.validate(
            description=source,
            experience_quotes=[TEXT, "Ce produit est 100% écologique et sans aucun impact."],
            claims_to_check=[{"quote": claim, "issue": "absolute_eco_claim"}],
        )
        self.assertNotIn(claim, result["description"])
        self.assertEqual(result["warnings"][0]["quote"], claim)
        self.assertIn("à préciser ou retirer", result["warnings"][0]["message"])

    def test_independent_absolute_claim_check_and_invented_warning_filter(self):
        result = self.validate(description=TEXT + " C'est zéro impact.", claims_to_check=[{"quote": "Not in the text", "issue": "certification"}])
        self.assertEqual([w["quote"] for w in result["warnings"]], ["zéro impact"])


@override_settings(GEMINI_API_KEY="test-key", PLACES_GEMINI_MODEL="test-preparation")
class PreparationWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="draft-user", email="draft@example.test")
        cls.other = get_user_model().objects.create_user(username="other-draft", email="other-draft@example.test")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)
        self.provider_patch = patch("places.recommendation_ai.generate_json", return_value=json.dumps(preparation()))
        self.provider = self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        self.url = reverse("places:recommendation-prepare")

    def test_ai_prepares_fields_without_creating_or_publishing_a_record(self):
        response = self.client.post(self.url, {"description": TEXT})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["category"], "home")
        self.assertEqual(response.json()["product_name"], "gourde inox")
        self.assertFalse(ProductRecommendation.objects.exists())

    def test_applying_prepared_fields_still_submits_through_normal_moderation(self):
        result = self.client.post(self.url, {"description": TEXT}).json()
        response = self.client.post(reverse("places:recommendation-create"), {
            **{key: result[key] for key in ("product_name", "category", "description")},
            "status": "approved", "user": self.other.pk,
        })
        recommendation = ProductRecommendation.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(recommendation.status, "pending")
        self.assertEqual(recommendation.user, self.user)

    def test_private_draft_cache_is_per_user_and_different_requests_are_throttled(self):
        self.assertFalse(self.client.post(self.url, {"description": TEXT}).json()["cached"])
        self.assertTrue(self.client.post(self.url, {"description": TEXT}).json()["cached"])
        self.assertEqual(self.client.post(self.url, {"description": TEXT + " Une nouvelle version."}).status_code, 429)
        self.client.force_login(self.other)
        self.assertFalse(self.client.post(self.url, {"description": TEXT}).json()["cached"])
        self.assertEqual(self.provider.call_count, 2)

    def test_provider_only_receives_draft_text_not_account_or_place_fields(self):
        self.client.post(self.url, {"description": TEXT, "place": "999", "user": self.other.pk, "status": "approved"})
        self.assertEqual(self.provider.call_args.args, (TEXT,))
        self.assertNotIn(self.user.email, str(self.provider.call_args))

    def test_endpoint_requires_authentication_post_csrf_and_valid_text(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"description": TEXT}).status_code, 302)
        self.client.force_login(self.user)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"description": TEXT}).status_code, 403)
        for text in ("", "Too short", "x" * 3001):
            self.assertEqual(self.client.post(self.url, {"description": text}).status_code, 400)
        self.provider.assert_not_called()

    def test_malformed_and_unavailable_ai_leave_the_form_editable(self):
        for value in ("not json", json.dumps(preparation(category="invalid"))):
            cache.clear()
            self.provider.return_value = value
            self.assertEqual(self.client.post(self.url, {"description": TEXT}).status_code, 503)
        cache.clear()
        self.provider.side_effect = GeminiUnavailableError("private-detail-test-key")
        response = self.client.post(self.url, {"description": TEXT})
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "private-detail", status_code=503)
        self.assertContains(self.client.get(reverse("places:recommendation-create")), "Préparer mon brouillon")
