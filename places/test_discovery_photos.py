import json
from io import BytesIO, StringIO
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .forms import GuideForm, PlaceFilterForm, RecommendationForm
from .models import Place, ProductRecommendation
from .services import find_places


def photo():
    content = BytesIO()
    Image.new("RGB", (20, 20), "green").save(content, format="PNG")
    return SimpleUploadedFile("avis.png", content.getvalue(), content_type="image/png")


class DiscoveryAndPhotosTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = self.settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(username="photo-user", email="photo@example.test")
        self.client.force_login(self.user)
        self.park = Place.objects.create(name="Parc du quartier", category="park", address="Tunis, Tunisie", latitude="36.82", longitude="10.17")
        self.distant = Place.objects.create(name="Parc éloigné", category="park", address="Bizerte, Tunisie", latitude="37.27", longitude="9.87")

    def test_named_origin_drives_distance_filter_without_exposing_coordinates(self):
        form = PlaceFilterForm({"near_place": self.park.pk, "radius": "5"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual([p.pk for p in find_places(form.cleaned_data)], [self.park.pk])
        self.assertEqual(form.location_label, self.park.name)
        self.assertTrue(form["latitude"].is_hidden)
        self.assertTrue(form["longitude"].is_hidden)
        self.assertEqual(form.cleaned_data["latitude"], Decimal(self.park.latitude))

    def test_city_filter_and_invalid_named_origin(self):
        form = PlaceFilterForm({"city": "Bizerte"})
        self.assertTrue(form.is_valid())
        self.assertEqual([p.pk for p in find_places(form.cleaned_data)], [self.distant.pk])
        self.assertFalse(PlaceFilterForm({"near_place": 999999, "radius": "5"}).is_valid())
        tunis = PlaceFilterForm({"city": "Tunis"})
        self.assertTrue(tunis.is_valid())
        self.assertEqual([p.pk for p in find_places(tunis.cleaned_data)], [self.park.pk])

    def test_activity_supplies_query_and_custom_request_takes_precedence(self):
        form = GuideForm({"activity": "walk"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn("promenade", form.cleaned_data["query"])
        custom = GuideForm({"activity": "walk", "query": "Un parc pour lire"})
        self.assertTrue(custom.is_valid())
        self.assertEqual(custom.cleaned_data["query"], "Un parc pour lire")
        self.assertFalse(GuideForm({}).is_valid())

    @patch("places.guide.generate_json", side_effect=AssertionError("No provider expected without API key"))
    def test_async_guide_accepts_named_origin_without_async_orm_access(self, provider):
        with self.settings(GEMINI_API_KEY=""):
            response = self.client.post(reverse("places:guide-search"), {"activity": "walk", "near_place": self.park.pk, "radius": "5"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["id"] for p in response.json()["places"]], [self.park.pk])
        with self.settings(GEMINI_API_KEY=""):
            city = self.client.post(reverse("places:guide-search"), {"activity": "walk", "city": "Tunis"})
        self.assertEqual([p["id"] for p in city.json()["places"]], [self.park.pk])

    def test_photo_submission_keeps_normal_moderation_and_is_displayed(self):
        response = self.client.post(reverse("places:recommendation-create"), {
            "product_name": "Un bocal", "description": "Je garde ce bocal pour ranger mes aliments.", "category": "home", "image": photo(),
        })
        self.assertEqual(response.status_code, 302)
        item = ProductRecommendation.objects.get()
        self.assertEqual(item.user, self.user)
        self.assertEqual(item.status, "pending")
        self.assertTrue(item.image.storage.exists(item.image.name))
        self.assertContains(self.client.get(item.get_absolute_url()), item.image.url)
        self.assertNotContains(self.client.get(reverse("places:recommendations")), item.product_name)

    def test_invalid_upload_and_size_limit(self):
        payload = {"product_name": "Bocal", "description": "Un avis", "category": "home"}
        invalid = RecommendationForm(payload, {"image": SimpleUploadedFile("fake.png", b"not a photo", content_type="image/png")})
        self.assertFalse(invalid.is_valid())
        self.assertIn("image", invalid.errors)
        oversized = photo()
        oversized.size = 6 * 1024 * 1024
        large = RecommendationForm(payload, {"image": oversized})
        self.assertFalse(large.is_valid())
        self.assertIn("5 Mo", str(large.errors))

    def test_replacing_a_photo_clears_old_source_credit(self):
        item = ProductRecommendation.objects.create(user=self.user, product_name="Bocal", description="Un avis", category="home", image_credit="Original author", image_source="https://example.org/photo")
        form = RecommendationForm({"product_name": item.product_name, "description": item.description, "category": item.category}, {"image": photo()}, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.image_credit, "")
        self.assertEqual(updated.image_source, "")

    def test_catalogue_replaces_known_placeholders_preserves_real_records_and_has_photos(self):
        legacy = Place.objects.create(name="Démo · Jardin partagé", category="park", address="Adresse fictive de démonstration", latitude=0, longitude=0)
        old_product = ProductRecommendation.objects.create(user=self.user, product_name="Démo · Gourde réutilisable", description="Old placeholder", category="home", place=legacy)
        output = StringIO()
        call_command("load_places_catalogue", stdout=output)
        counts = (Place.objects.count(), ProductRecommendation.objects.count())
        call_command("load_places_catalogue", stdout=output)
        self.assertEqual(counts, (Place.objects.count(), ProductRecommendation.objects.count()))
        legacy.refresh_from_db()
        old_product.refresh_from_db()
        self.assertEqual(legacy.name, "Parc du Belvédère")
        self.assertIsNone(old_product.place)
        self.assertEqual(old_product.status, "approved")
        self.assertEqual(Place.objects.get(pk=self.park.pk).name, "Parc du quartier")
        for item in [legacy, *ProductRecommendation.objects.all()]:
            self.assertTrue(item.image.storage.exists(item.image.name))
        self.assertFalse(Place.objects.filter(name__icontains="démo").exists())
        self.assertFalse(ProductRecommendation.objects.filter(product_name__icontains="démo").exists())
