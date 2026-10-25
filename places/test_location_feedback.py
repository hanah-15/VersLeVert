import json
from decimal import Decimal
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .forms import PlaceFilterForm, RecommendationForm
from .geolocation import read_location_label
from .models import Place, ProductRecommendation
from .recommendation_ai import RecommendationPreparation, verified_preparation
from .services import find_places
from .test_recommendation_ai import preparation


class AreaLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="area-user", email="area@example.test")
        self.client.force_login(self.user)
        self.url = reverse("places:locate-area")
        # Public neighbourhood centre used for fixtures, not a user's GPS.
        self.point = {"latitude": "36.742946", "longitude": "10.250764"}
        self.provider = patch("places.geolocation.httpx.get")
        self.get = self.provider.start()
        self.addCleanup(self.provider.stop)
        self.get.return_value = httpx.Response(200, request=httpx.Request("GET", "https://nominatim.openstreetmap.org/reverse"), json={"address": {"suburb": "Nouvelle Médina", "city": "Ben Arous"}})

    def test_area_label_is_cached_and_external_coordinates_are_approximate(self):
        response = self.client.post(self.url, self.point)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "Nouvelle Médina, Ben Arous")
        params = self.get.call_args.kwargs["params"]
        self.assertEqual(params["lat"], 36.743)
        self.assertEqual(params["lon"], 10.251)
        self.assertNotIn(self.user.email, str(self.get.call_args))
        self.assertEqual(self.client.post(self.url, self.point).status_code, 200)
        self.get.assert_called_once()

    def test_signed_area_label_survives_radius_selection_but_not_a_different_position(self):
        data = {**self.point, **self.client.post(self.url, self.point).json(), "radius": "5"}
        form = PlaceFilterForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.location_label, "Nouvelle Médina, Ben Arous")
        form25 = PlaceFilterForm({**data, "radius": "25"})
        self.assertTrue(form25.is_valid())
        self.assertEqual(form25.location_label, form.location_label)
        tampered = {**form.cleaned_data, "latitude": Decimal("37.5")}
        self.assertEqual(read_location_label(tampered), "")
        self.assertEqual(read_location_label({**form.cleaned_data, "location_token": "forged"}), "")
        response = self.client.get(reverse("places:index"), data)
        self.assertContains(response, "Nouvelle Médina, Ben Arous")
        self.assertContains(response, "Afficher les lieux")

    def test_radius_still_filters_the_exact_position(self):
        near = Place.objects.create(name="Parc voisin", category="park", address="Ben Arous", latitude="36.743", longitude="10.251")
        Place.objects.create(name="Parc éloigné", category="park", address="Bizerte", latitude="37.27", longitude="9.87")
        response = self.client.post(self.url, self.point).json()
        form = PlaceFilterForm({**self.point, "location_token": response["location_token"], "radius": "1"})
        self.assertTrue(form.is_valid())
        self.assertEqual([p.pk for p in find_places(form.cleaned_data)], [near.pk])

    def test_provider_failures_are_sanitized_and_negatively_cached(self):
        self.get.side_effect = httpx.TimeoutException("private details")
        for _ in range(2):
            response = self.client.post(self.url, self.point)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private details", response.content.decode())
        self.get.assert_called_once()

    def test_global_gate_prevents_bursts_and_auth_post_csrf_validation_are_required(self):
        self.assertEqual(self.client.post(self.url, self.point).status_code, 200)
        self.assertEqual(self.client.post(self.url, {**self.point, "latitude": "37.2"}).status_code, 503)
        self.get.assert_called_once()
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, {"latitude": 91, "longitude": 10}).status_code, 400)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(self.url, self.point).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.point).status_code, 302)


class WrittenPurchaseLocationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="shop-user", email="shop@example.test")
        self.client.force_login(self.user)
        self.place = Place.objects.create(name="Boutique du quartier", category="zero_waste_shop", address="Tunis", latitude=36.8, longitude=10.2)
        self.payload = {"product_name": "Savon", "category": "personal_care", "description": "Un savon que je trouve abordable et agréable.", "purchase_location": "Monoprix, Nouvelle Médina"}

    def test_free_location_saves_without_creating_a_place_and_remains_pending(self):
        response = self.client.post(reverse("places:recommendation-create"), self.payload)
        self.assertEqual(response.status_code, 302)
        item = ProductRecommendation.objects.get()
        self.assertEqual(item.purchase_location, self.payload["purchase_location"])
        self.assertIsNone(item.place)
        self.assertEqual(item.status, "pending")
        self.assertEqual(Place.objects.count(), 1)
        self.assertContains(self.client.get(item.get_absolute_url()), "Monoprix, Nouvelle Médina")

    def test_exact_catalogue_names_link_and_custom_text_overrides_stale_hidden_place(self):
        form = RecommendationForm({**self.payload, "purchase_location": self.place.name})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["place"], self.place)
        custom = RecommendationForm({**self.payload, "place": self.place.pk})
        self.assertTrue(custom.is_valid())
        self.assertIsNone(custom.cleaned_data["place"])
        cleared = RecommendationForm({**self.payload, "purchase_location": "", "place": self.place.pk})
        self.assertTrue(cleared.is_valid())
        self.assertIsNone(cleared.cleaned_data["place"])
        legacy = RecommendationForm({key: value for key, value in {**self.payload, "place": self.place.pk}.items() if key != "purchase_location"})
        self.assertTrue(legacy.is_valid())
        self.assertEqual(legacy.cleaned_data["place"], self.place)

    def test_free_location_is_searchable_and_visible_in_published_api(self):
        item = ProductRecommendation.objects.create(user=self.user, status="approved", **self.payload)
        response = self.client.get(reverse("places:recommendations"), {"q": "Nouvelle Médina"})
        self.assertContains(response, item.product_name)
        api = self.client.get(reverse("places:api-recommendations"), {"q": "Nouvelle Médina"}).json()
        self.assertEqual(api["results"][0]["purchase_location"], self.payload["purchase_location"])

    def test_guide_can_filter_free_location_by_city_without_inventing_a_distance(self):
        item = ProductRecommendation.objects.create(user=self.user, status="approved", **self.payload)
        with self.settings(GEMINI_API_KEY=""):
            response = self.client.post(reverse("places:guide-search"), {"query": "Un savon", "city": "Nouvelle Médina"})
        self.assertEqual([p["id"] for p in response.json()["products"]], [item.pk])
        self.assertIsNone(response.json()["products"][0]["distance_km"])
        with self.settings(GEMINI_API_KEY=""):
            response = self.client.post(reverse("places:guide-search"), {"query": "Un savon", "latitude": 36.74, "longitude": 10.25, "radius": 10})
        self.assertEqual(response.json()["products"], [])

    def test_ai_location_requires_an_exact_source_quote_and_name(self):
        source = "This soap smells good. I bought it at Monoprix in Nouvelle Medina."
        data = preparation(product_name="soap", category="personal_care", experience_quotes=[], purchase_location="Monoprix in Nouvelle Medina", location_quote="I bought it at Monoprix in Nouvelle Medina.")
        result = verified_preparation(RecommendationPreparation.model_validate(data), "soap", source)
        self.assertEqual(result["purchase_location"], "Monoprix in Nouvelle Medina")
        data["purchase_location"] = "Invented Shop"
        self.assertEqual(verified_preparation(RecommendationPreparation.model_validate(data), "soap", source)["purchase_location"], "")

    def test_translated_feedback_keeps_price_value_scent_and_cautious_packaging(self):
        source = "Cheap and healthy and its packaging is safe for environment so its worth to buy and smells good"
        data = preparation(product_name="Savon", category="personal_care", experience_quotes=[], claims_to_check=[{"quote": "healthy", "issue": "health_claim"}, {"quote": "packaging is safe for environment", "issue": "absolute_eco_claim"}], rewritten_sentences=[
            {"text": "Je trouve ce savon abordable et son parfum agréable, c'est un achat qui en vaut la peine.", "source_quotes": ["Cheap", "smells good", "worth to buy"]},
            {"text": "Son emballage me semble intéressant pour l'environnement, mais cela reste à vérifier.", "source_quotes": ["packaging is safe for environment"]},
        ])
        result = verified_preparation(RecommendationPreparation.model_validate(data), "Savon", source)
        for point in ("abordable", "parfum", "vaut la peine", "emballage"):
            self.assertIn(point, result["description"])
        self.assertNotIn("bon pour la santé", result["description"])
