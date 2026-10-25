import asyncio
import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from google.genai.errors import ServerError

from .ai import GeminiUnavailableError, generate_json
from .forms import GuideForm, RecommendationForm
from .guide import SearchIntent, search_catalogue
from .models import Place, ProductRecommendation


def intent(**changes):
    return {
        "objective": "Un jardin pour une pause nature", "target": "both",
        "keywords": ["jardin", "parc", "nature", "gourde"], "place_categories": ["park"],
        "product_categories": [], "excluded_place_categories": [], "location": "",
        "unavailable_information": [], **changes,
    }


@override_settings(GEMINI_API_KEY="test-key", PLACES_GEMINI_MODEL="test-guide-model")
class GuideIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="guide-user", email="private-guide@example.test")
        cls.park = Place.objects.create(name="Jardin local", category="park", description="Tables de pique-nique sous les arbres.", address="Tunis", latitude="36.8065", longitude="10.1815")
        cls.far_park = Place.objects.create(name="Jardin lointain", category="park", address="Sousse", latitude="35.8256", longitude="10.6084")
        cls.product = ProductRecommendation.objects.create(user=cls.user, product_name="Gourde inox", category="home", description="Une gourde réutilisable.", place=cls.park, status="approved")
        cls.private = ProductRecommendation.objects.create(user=cls.user, product_name="SECRET_PENDING", category="home", description="SECRET_DESCRIPTION")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)
        self.provider_patch = patch("places.guide.generate_json", return_value=json.dumps(intent()))
        self.provider = self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)

    def search(self, query="Une pause nature avec une gourde", **filters):
        return async_to_sync(search_catalogue)({"query": query, **filters})

    def test_semantic_search_retrieves_a_matching_place_beyond_the_old_forty_limit(self):
        Place.objects.bulk_create([
            Place(name=f"AAA {index}", category="cafe", address="Tunis", latitude=36, longitude=10)
            for index in range(45)
        ])
        self.provider.return_value = json.dumps(intent(target="places", keywords=["pique-nique"], place_categories=["park"]))
        result = self.search("Me poser au vert pour manger dehors")
        self.assertIn(self.park.pk, [p["id"] for p in result["places"]])
        self.assertEqual(result["catalogue_counts"]["places"], 47)
        self.assertEqual(result["source"], "gemini")

    def test_provider_receives_only_the_question_not_records_identity_or_coordinates(self):
        query = "Un parc pour une promenade"
        self.search(query, latitude=36.8065, longitude=10.1815, radius=5)
        self.assertEqual(self.provider.call_args.args, (query,))
        sent = str(self.provider.call_args)
        for value in ("SECRET_PENDING", "SECRET_DESCRIPTION", self.user.email, "36.8065", "Gourde inox"):
            self.assertNotIn(value, sent)

    def test_every_result_uses_database_name_link_and_exact_evidence(self):
        result = self.search()
        row = next(p for p in result["places"] if p["id"] == self.park.pk)
        self.assertEqual(row["name"], self.park.name)
        self.assertEqual(row["url"], self.park.get_absolute_url())
        self.assertEqual(row["evidence"][1]["text"], self.park.description)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_city_and_radius_are_hard_filters_for_places_and_products(self):
        result = self.search(city="Sousse")
        self.assertEqual([p["id"] for p in result["places"]], [self.far_park.pk])
        self.assertEqual(result["products"], [])
        result = self.search(latitude=36.8065, longitude=10.1815, radius=2)
        self.assertEqual([p["id"] for p in result["places"]], [self.park.pk])
        self.assertEqual([p["id"] for p in result["products"]], [self.product.pk])
        self.assertEqual(result["places"][0]["distance_km"], 0)

    def test_position_orders_relevant_results_by_distance(self):
        result = self.search(latitude=35.8256, longitude=10.6084)
        self.assertEqual([p["id"] for p in result["places"]], [self.far_park.pk, self.park.pk])

    def test_category_and_explicit_exclusions_are_applied(self):
        self.assertEqual(self.search(category="cafe")["places"], [])
        self.provider.return_value = json.dumps(intent(excluded_place_categories=["park"]))
        cache.clear()
        result = self.search()
        self.assertEqual(result["places"], [])
        self.assertEqual(result["products"], [])

    def test_model_cannot_silently_invent_a_city_filter(self):
        self.provider.return_value = json.dumps(intent(location="Berlin"))
        self.assertEqual(self.search("Un parc")["filters"]["city"], "")
        cache.clear()
        self.provider.return_value = json.dumps(intent(location="Sousse"))
        self.assertEqual(self.search("Un parc à Sousse")["filters"]["city"], "Sousse")

    def test_cached_understanding_rechecks_publication_status(self):
        self.assertTrue(self.search()["products"])
        self.product.status = "pending"
        self.product.save(update_fields=["status"])
        result = self.search()
        self.assertTrue(result["cached"])
        self.assertEqual(result["products"], [])
        self.assertEqual(self.provider.call_count, 1)

    def test_unavailable_or_invalid_provider_yields_labelled_local_search(self):
        for raw in ("not json", json.dumps({**intent(), "places": [{"id": 999999}]}), json.dumps(intent(place_categories=["invented"]))):
            with self.subTest(raw=raw):
                cache.clear()
                self.provider.return_value = raw
                self.assertEqual(self.search("Un jardin")["source"], "fallback")
        self.provider.side_effect = GeminiUnavailableError("private-provider-detail")
        result = self.search("Un jardin")
        self.assertEqual(result["source"], "fallback")
        self.assertNotIn("private-provider-detail", json.dumps(result))

    def test_unrelated_request_returns_no_fabricated_suggestions(self):
        self.provider.return_value = json.dumps(intent(keywords=[], place_categories=[], product_categories=[]))
        result = self.search("Un ordinateur quantique introuvable")
        self.assertEqual(result["places"], [])
        self.assertEqual(result["products"], [])

    def test_hours_are_reported_as_unknown_not_guessed(self):
        self.provider.return_value = json.dumps(intent(unavailable_information=["opening_hours"]))
        self.assertIn("Les horaires d'ouverture ne sont pas renseignés.", self.search()["warnings"])

    def test_async_endpoint_requires_login_post_csrf_and_valid_filters(self):
        url = reverse("places:guide-search")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(url, {"query": "Un parc"}).status_code, 302)
        self.client.force_login(self.user)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(url, {"query": "Un parc"}).status_code, 403)
        for data in ({"query": ""}, {"query": "x" * 501}, {"query": "Parc", "latitude": "91", "longitude": "10"}, {"query": "Parc", "radius": "5"}):
            self.assertEqual(self.client.post(url, data).status_code, 400)
        self.provider.assert_not_called()

    def test_async_endpoint_cache_and_rate_limit(self):
        url = reverse("places:guide-search")
        first = self.client.post(url, {"query": "Un parc"})
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, "Pourquoi cette suggestion")
        again = self.client.post(url, {"query": "Un parc"})
        self.assertTrue(again.json()["cached"])
        self.assertEqual(self.client.post(url, {"query": "Un autre parc"}).status_code, 429)
        self.assertEqual(self.provider.call_count, 1)

    def test_html_and_fetch_escape_untrusted_objectives_and_catalogue_text(self):
        self.park.description = "<script>bad()</script>"
        self.park.save(update_fields=["description"])
        self.provider.return_value = json.dumps(intent(objective="<img src=x onerror=bad()>"))
        for url in (reverse("places:guide-search"), reverse("places:guide")):
            response = self.client.post(url, {"query": "Un jardin"})
            content = response.json()["html"] if response.headers["Content-Type"].startswith("application/json") else response.content.decode()
            self.assertNotIn("<script>", content)
            self.assertNotIn("<img src=x", content)
            self.assertIn("&lt;script&gt;", content)
            self.assertIn("&lt;img", content)

    def test_catalogue_import_is_idempotent_and_has_no_usable_login(self):
        output = StringIO()
        call_command("load_places_catalogue", stdout=output)
        count = Place.objects.count()
        call_command("load_places_catalogue", stdout=output)
        self.assertEqual(Place.objects.count(), count)
        self.assertFalse(get_user_model().objects.get(username="places-catalogue").has_usable_password())


class GuideFormTests(SimpleTestCase):
    def test_help_and_error_references_point_to_the_template_ids(self):
        field = RecommendationForm()["description"]
        self.assertEqual(field.field.widget.attrs["aria-describedby"], "id_description_helptext")
        form = GuideForm({"query": "Un parc", "latitude": "91"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form["latitude"].field.widget.attrs["aria-describedby"], "id_latitude_error")

    @override_settings(GEMINI_API_KEY="test-key")
    def test_independent_requests_can_await_the_provider_concurrently(self):
        from .guide import understand_query

        async def run():
            started = 0
            both_started = asyncio.Event()

            async def provider(*args, **kwargs):
                nonlocal started
                started += 1
                if started == 2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=2)
                return json.dumps(intent())

            with patch("places.guide.generate_json", side_effect=provider):
                return await asyncio.gather(
                    understand_query("Une demande", use_cache=False),
                    understand_query("Une autre demande", use_cache=False),
                )

        results = asyncio.run(run())
        self.assertEqual([row[1] for row in results], ["gemini", "gemini"])


@override_settings(GEMINI_API_KEY="test-key", PLACES_GEMINI_MODEL="test-guide-model", PLACES_GEMINI_TIMEOUT_SECONDS=15)
class StructuredProviderTests(SimpleTestCase):
    def setUp(self):
        self.client_patch = patch("places.ai.genai.Client")
        self.client_class = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = self.client_class.return_value.__enter__.return_value
        self.client.aio.__aenter__ = AsyncMock(return_value=self.client.aio)
        self.client.aio.__aexit__ = AsyncMock(return_value=False)
        self.generate = AsyncMock(return_value=SimpleNamespace(text=json.dumps(intent())))
        self.client.aio.models.generate_content = self.generate

    def call(self):
        return async_to_sync(generate_json)("Un jardin", system_instruction="Extract a search", schema=SearchIntent.model_json_schema())

    def test_async_structured_request_uses_separate_model_and_closes_clients(self):
        self.assertEqual(json.loads(self.call())["place_categories"], ["park"])
        self.assertEqual(self.generate.call_args.kwargs["model"], "test-guide-model")
        self.assertEqual(self.generate.call_args.kwargs["config"].response_mime_type, "application/json")
        self.client_class.return_value.__exit__.assert_called_once()
        self.client.aio.__aexit__.assert_awaited_once()

    def test_provider_timeout_and_http_failures_are_sanitized(self):
        for error in (TimeoutError("private-details"), ServerError(503, {"error": {"message": "secret-key"}})):
            with self.subTest(error=type(error).__name__):
                self.generate.side_effect = error
                with self.assertRaises(GeminiUnavailableError) as caught:
                    self.call()
                self.assertNotIn("private-details", str(caught.exception))
                self.assertNotIn("secret-key", str(caught.exception))

    def test_empty_response_is_unavailable(self):
        self.generate.return_value = SimpleNamespace(text=None)
        with self.assertRaises(GeminiUnavailableError):
            self.call()
