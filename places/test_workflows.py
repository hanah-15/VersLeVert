import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .ai import GeminiUnavailableError
from .forms import PlaceFilterForm
from .models import Place, ProductRecommendation, RecommendationLike
from .services import suggest_from_catalogue


class PlacesWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="owner", email="owner@example.com", password="test-password-123")
        cls.other = User.objects.create_user(username="other", email="other@example.com", password="test-password-123")
        cls.staff = User.objects.create_user(username="staff", email="staff@example.com", password="test-password-123", is_staff=True)
        cls.park = Place.objects.create(name="Parc Démo", category="park", address="Adresse A", latitude="36.806500", longitude="10.181500", created_by=cls.staff)
        cls.cafe = Place.objects.create(name="Café Démo", category="cafe", address="Adresse B", latitude="36.816500", longitude="10.181500")
        cls.shop = Place.objects.create(name="Boutique Démo", category="zero_waste_shop", address="Adresse C", latitude="35.825600", longitude="10.608400")
        cls.approved = ProductRecommendation.objects.create(user=cls.owner, product_name="Gourde réutilisable", category="home", description="Mon expérience avec ce produit.", place=cls.shop, status="approved")
        cls.pending = ProductRecommendation.objects.create(user=cls.owner, product_name="Produit privé en attente", category="other", description="SECRET_PENDING")
        cls.rejected = ProductRecommendation.objects.create(user=cls.owner, product_name="Produit refusé", category="other", description="À compléter", status="rejected", rejection_reason="Précisez votre expérience.")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.owner)

    def place_data(self, **overrides):
        return {"name": "Nouveau lieu", "category": "park", "description": "Une description.", "address": "Adresse de test", "latitude": "36.80", "longitude": "10.18", **overrides}

    def recommendation_data(self, **overrides):
        return {"product_name": "Savon solide", "category": "personal_care", "description": "Moins d’emballages dans mon quotidien.", "place": self.shop.pk, **overrides}

    def test_visitors_are_redirected_from_module_pages(self):
        self.client.logout()
        for name in ("index", "recommendations", "my-recommendations", "guide", "create", "moderation"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"places:{name}"))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_catalogue_search_category_and_distance_sorting(self):
        response = self.client.get(reverse("places:index"), {"latitude": "36.8065", "longitude": "10.1815", "radius": "5"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([place.pk for place in response.context["places"]], [self.park.pk, self.cafe.pk])
        self.assertContains(response, "0.0 km")
        response = self.client.get(reverse("places:index"), {"category": "cafe", "q": "Adresse B"})
        self.assertEqual([place.pk for place in response.context["places"]], [self.cafe.pk])

    def test_invalid_coordinate_pair_and_radius_are_rejected(self):
        for data in ({"latitude": "91", "longitude": "10"}, {"latitude": "36"}, {"radius": "5"}, {"category": "fake"}):
            with self.subTest(data=data):
                response = self.client.get(reverse("places:index"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filter_form"].errors)
                self.assertEqual(response.context["paginator"].count, 0)
        form = PlaceFilterForm({"latitude": "0", "longitude": "0"})
        self.assertTrue(form.is_valid())

    def test_place_pagination_preserves_search(self):
        Place.objects.bulk_create([Place(name=f"Test {i}", category="park", address="Test", latitude=0, longitude=0) for i in range(13)])
        response = self.client.get(reverse("places:index"), {"q": "Test", "page": "2"})
        self.assertEqual(len(response.context["places"]), 1)
        self.assertContains(response, "q=Test")

    def test_normal_user_cannot_manage_places_or_moderation_even_by_post(self):
        routes = [("create", None), ("update", self.park.pk), ("delete", self.park.pk), ("moderation", None), ("recommendation-moderate", self.pending.pk)]
        for name, pk in routes:
            url = reverse(f"places:{name}", args=[pk] if pk else [])
            for method in (self.client.get, self.client.post):
                with self.subTest(route=name, method=method.__name__):
                    self.assertEqual(method(url).status_code, 403)

    def test_staff_can_create_update_and_delete_places(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("places:create"), self.place_data())
        place = Place.objects.get(name="Nouveau lieu")
        self.assertRedirects(response, place.get_absolute_url())
        self.assertEqual(place.created_by, self.staff)
        response = self.client.post(reverse("places:update", args=[place.pk]), self.place_data(name="Lieu modifié"))
        self.assertEqual(response.status_code, 302)
        place.refresh_from_db()
        self.assertEqual(place.name, "Lieu modifié")
        self.assertEqual(self.client.get(reverse("places:delete", args=[place.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("places:delete", args=[place.pk])).status_code, 302)
        self.assertFalse(Place.objects.filter(pk=place.pk).exists())

    def test_invalid_place_is_not_saved_and_errors_render(self):
        self.client.force_login(self.staff)
        count = Place.objects.count()
        response = self.client.post(reverse("places:create"), self.place_data(latitude="91", address=""))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertEqual(Place.objects.count(), count)

    def test_coordinate_model_and_database_constraints(self):
        self.park.latitude = 91
        with self.assertRaises(ValidationError):
            self.park.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Place.objects.filter(pk=self.park.pk).update(latitude=91)

    def test_place_deletion_preserves_associated_recommendations(self):
        self.shop.delete()
        self.approved.refresh_from_db()
        self.assertIsNone(self.approved.place_id)

    def test_new_recommendation_ignores_forged_author_and_status(self):
        response = self.client.post(reverse("places:recommendation-create"), self.recommendation_data(user=self.other.pk, status="approved", moderated_by=self.staff.pk))
        recommendation = ProductRecommendation.objects.get(product_name="Savon solide")
        self.assertRedirects(response, recommendation.get_absolute_url())
        self.assertEqual(recommendation.user, self.owner)
        self.assertEqual(recommendation.status, "pending")
        self.assertIsNone(recommendation.moderated_by)

    def test_unpublished_recommendations_are_private(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("places:recommendations"))
        self.assertContains(response, self.approved.product_name)
        self.assertNotContains(response, self.pending.product_name)
        for rec in (self.pending, self.rejected):
            self.assertEqual(self.client.get(rec.get_absolute_url()).status_code, 404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("places:my-recommendations")), self.pending.product_name)
        self.assertContains(self.client.get(self.rejected.get_absolute_url()), self.rejected.rejection_reason)

    def test_staff_can_review_pending_content(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("places:moderation")), self.pending.product_name)
        self.assertEqual(self.client.get(self.pending.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(reverse("places:recommendation-moderate", args=[self.pending.pk])).status_code, 200)

    def test_rejection_requires_reason_and_approval_records_audit(self):
        self.client.force_login(self.staff)
        url = reverse("places:recommendation-moderate", args=[self.pending.pk])
        response = self.client.post(url, {"decision": "rejected", "rejection_reason": " "})
        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, "pending")
        self.client.post(url, {"decision": "rejected", "rejection_reason": "Ajoutez des détails."})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.rejection_reason, "Ajoutez des détails.")
        self.client.post(url, {"decision": "approved", "rejection_reason": "ignored"})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, "approved")
        self.assertEqual(self.pending.rejection_reason, "")
        self.assertEqual(self.pending.moderated_by, self.staff)
        self.assertIsNotNone(self.pending.moderated_at)

    def test_rejected_model_requires_nonblank_reason(self):
        self.pending.status = "rejected"
        self.pending.rejection_reason = " "
        with self.assertRaises(ValidationError):
            self.pending.full_clean()

    def test_owner_edit_resets_moderation_and_likes(self):
        RecommendationLike.objects.create(recommendation=self.approved, user=self.other)
        self.client.post(reverse("places:recommendation-update", args=[self.approved.pk]), self.recommendation_data())
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, "pending")
        self.assertEqual(self.approved.product_name, "Savon solide")
        self.assertIsNone(self.approved.moderated_by)
        self.assertEqual(self.approved.likes.count(), 0)

    def test_other_users_cannot_edit_or_delete_recommendation(self):
        self.client.force_login(self.other)
        for action in ("recommendation-update", "recommendation-delete"):
            url = reverse(f"places:{action}", args=[self.approved.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.recommendation_data()).status_code, 404)
        self.assertTrue(ProductRecommendation.objects.filter(pk=self.approved.pk).exists())

    def test_owner_can_delete_recommendation(self):
        url = reverse("places:recommendation-delete", args=[self.pending.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(ProductRecommendation.objects.filter(pk=self.pending.pk).exists())

    def test_like_toggle_requires_post_and_does_not_duplicate(self):
        url = reverse("places:recommendation-like", args=[self.approved.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.assertEqual(self.approved.likes.count(), 1)
        self.assertContains(self.client.get(self.approved.get_absolute_url()), 'aria-pressed="true"')
        self.client.post(url)
        self.assertEqual(self.approved.likes.count(), 0)

    def test_pending_products_cannot_be_liked_and_redirect_is_safe(self):
        self.assertEqual(self.client.post(reverse("places:recommendation-like", args=[self.pending.pk])).status_code, 404)
        response = self.client.post(reverse("places:recommendation-like", args=[self.approved.pk]), {"next": "https://evil.example/"})
        self.assertRedirects(response, self.approved.get_absolute_url())

    def test_like_uniqueness_is_enforced_by_database(self):
        RecommendationLike.objects.create(recommendation=self.approved, user=self.owner)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RecommendationLike.objects.create(recommendation=self.approved, user=self.owner)

    def test_write_routes_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse("places:recommendation-create"), self.recommendation_data()).status_code, 403)
        self.assertEqual(client.post(reverse("places:recommendation-like", args=[self.approved.pk])).status_code, 403)

    def test_all_user_pages_render(self):
        for url in (self.park.get_absolute_url(), self.approved.get_absolute_url(), reverse("places:recommendation-create"), reverse("places:recommendation-create")+f"?place={self.park.pk}", reverse("places:recommendation-update", args=[self.pending.pk]), reverse("places:guide")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_api_authentication_filtering_and_distance(self):
        url = reverse("places:api-places")
        self.client.logout()
        self.assertIn(self.client.get(url).status_code, (401, 403))
        self.client.force_login(self.owner)
        data = self.client.get(url, {"latitude": "36.8065", "longitude": "10.1815", "radius": "5"}).json()
        self.assertEqual([row["id"] for row in data["results"]], [self.park.pk, self.cafe.pk])
        self.assertAlmostEqual(data["results"][0]["distance"], 0)
        self.assertEqual(self.client.get(url, {"latitude": "bad"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("places:api-place-detail", args=[self.park.pk])).status_code, 200)

    def test_api_only_exposes_published_recommendations(self):
        response = self.client.get(reverse("places:api-recommendations"))
        self.assertEqual([row["id"] for row in response.json()["results"]], [self.approved.pk])
        self.assertNotIn("email", response.content.decode())
        self.assertEqual(self.client.get(reverse("places:api-recommendation-detail", args=[self.pending.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("places:api-recommendation-detail", args=[self.approved.pk])).status_code, 200)

    def test_recommendation_search_and_popularity_filters_match_api(self):
        RecommendationLike.objects.create(user=self.other, recommendation=self.approved)
        params = {"q": "Gourde", "category": "home", "sort": "popular"}
        response = self.client.get(reverse("places:recommendations"), params)
        self.assertEqual([item.pk for item in response.context["recommendations"]], [self.approved.pk])
        response = self.client.get(reverse("places:api-recommendations"), params)
        self.assertEqual([item["id"] for item in response.json()["results"]], [self.approved.pk])
        self.assertEqual(self.client.get(reverse("places:api-recommendations"), {"category": "unknown"}).status_code, 400)

    def test_django_admin_records_creator_and_moderator(self):
        # This account is privileged only inside the disposable Django test DB.
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_superuser"])
        self.client.force_login(self.staff)
        response = self.client.post(reverse("admin:places_place_add"), self.place_data(name="Lieu ajouté dans admin"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Place.objects.get(name="Lieu ajouté dans admin").created_by, self.staff)
        url = reverse("admin:places_productrecommendation_change", args=[self.pending.pk])
        response = self.client.post(url, self.recommendation_data(status="rejected", rejection_reason=""))
        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, "pending")
        response = self.client.post(url, self.recommendation_data(status="approved", rejection_reason=""))
        self.assertEqual(response.status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.moderated_by, self.staff)
        self.assertEqual(self.pending.status, "approved")
        self.assertEqual(self.client.get(reverse("admin:places_recommendationlike_add")).status_code, 403)

    @override_settings(GEMINI_API_KEY="")
    def test_guide_only_retrieves_public_catalogue_content(self):
        result = suggest_from_catalogue("Réduire les emballages")
        self.assertEqual([item["id"] for item in result["places"]], [self.shop.pk])
        self.assertNotIn("SECRET_PENDING", json.dumps(result))
        self.assertNotIn(self.pending.pk, [item["id"] for item in result["products"]])

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("places.guide.generate_json", return_value="not valid JSON")
    def test_malformed_ai_response_uses_labelled_fallback(self, generate):
        self.assertEqual(suggest_from_catalogue("Un produit")["source"], "fallback")

    @patch("places.guide.generate_json")
    def test_empty_catalogue_never_calls_gemini(self, generate):
        ProductRecommendation.objects.all().delete()
        Place.objects.all().delete()
        self.assertEqual(suggest_from_catalogue("Un lieu")["source"], "empty")
        generate.assert_not_called()
        self.assertContains(self.client.get(reverse("places:guide")), "catalogue est encore vide")

    @patch("places.views.suggest_from_catalogue")
    def test_guide_html_fallback_escapes_generated_text(self, suggest):
        suggest.return_value = {"summary": "<script>alert(1)</script>", "places": [], "products": []}
        response = self.client.post(reverse("places:guide"), {"query": "Un lieu"})
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    @patch("places.views.suggest_from_catalogue")
    def test_guide_json_contains_the_same_server_rendered_results(self, suggest):
        suggest.return_value = {"summary": "Voici une piste", "places": [], "products": []}
        url = reverse("places:guide")
        response = self.client.post(url, {"query": "Un lieu"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "Voici une piste")
        self.assertIn("html", response.json())
        self.assertEqual(suggest.call_count, 1)

    @patch("places.views.suggest_from_catalogue", side_effect=GeminiUnavailableError("provider detail"))
    def test_guide_failure_and_validation_are_clear(self, suggest):
        url = reverse("places:guide")
        self.assertEqual(self.client.post(url, {"query": ""}, HTTP_ACCEPT="application/json").status_code, 400)
        response = self.client.post(url, {"query": "Un produit"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("provider detail", response.content.decode())
        cache.clear()
        response = self.client.post(url, {"query": "Un produit"})
        self.assertContains(response, "momentanément indisponible")
