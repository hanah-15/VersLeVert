from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.utils import distance_km

from .forms import WasteRequestForm
from .models import Status, WasteRequest, WasteStatusLog, WasteType


User = get_user_model()


class WasteTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="declarant", password="password123", email="declarant@example.com"
        )
        self.other_user = User.objects.create_user(
            username="collecteur", password="password123", email="collecteur@example.com"
        )

    def make_request(self, user=None, **overrides):
        values = {
            "user": user or self.user,
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": Decimal("2.50"),
            "address": "Adresse exacte à Tunis",
            "latitude": 36.8065,
            "longitude": 10.1815,
        }
        values.update(overrides)
        return WasteRequest.objects.create(**values)

    def test_login_required_on_waste_index(self):
        response = self.client.get(reverse("waste:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_sees_only_own_requests(self):
        own_request = self.make_request()
        self.make_request(user=self.other_user, address="Adresse privée")
        self.client.force_login(self.user)

        response = self.client.get(reverse("waste:index"))

        self.assertEqual(list(response.context["requests"]), [own_request])

    def test_valid_creation_redirects_to_index(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("waste:create"), {
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": "2.5",
            "address": "Tunis",
            "latitude": "36.8065",
            "longitude": "10.1815",
        })

        self.assertRedirects(response, reverse("waste:index"))

    def test_empty_address_is_rejected(self):
        form = WasteRequestForm(data={
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": "2.5",
            "address": "",
            "latitude": "36.8065",
            "longitude": "10.1815",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Ce champ est obligatoire.", form.errors["address"])

    def test_zero_weight_is_rejected(self):
        form = WasteRequestForm(data={
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": "0",
            "address": "Tunis",
            "latitude": "36.8065",
            "longitude": "10.1815",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("estimated_weight", form.errors)

    def test_missing_position_is_rejected(self):
        form = WasteRequestForm(data={
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": "2.5",
            "address": "Tunis",
            "latitude": "",
            "longitude": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Choisissez la position sur la carte.", form.non_field_errors())

    def test_status_transitions_and_logs(self):
        request = self.make_request()
        request.change_status(Status.PLANNED, self.user)
        request.change_status(Status.REQUESTED, self.user)
        self.assertEqual(request.logs.count(), 2)
        self.assertEqual(request.status, Status.REQUESTED)

        request.change_status(Status.PLANNED, self.user)
        request.change_status(Status.COLLECTED, self.user)
        request.change_status(Status.CONFIRMED, self.user)
        with self.assertRaises(ValueError):
            request.change_status(Status.REQUESTED, self.user)

    def test_distance_is_plausible_for_tunis_nord(self):
        distance = distance_km(36.8065, 10.1815, 36.868, 10.1815)
        self.assertAlmostEqual(distance, 6.8, delta=0.5)

    def test_market_excludes_owner_and_hides_address(self):
        self.make_request()
        other_request = self.make_request(user=self.other_user, address="Adresse confidentielle")
        self.client.force_login(self.user)

        response = self.client.get(reverse("waste:market"))

        self.assertEqual([row["request"] for row in response.context["rows"]], [other_request])
        self.assertNotContains(response, "Adresse confidentielle")

    def test_market_sorts_by_distance_when_position_is_provided(self):
        near = self.make_request(user=self.other_user, address="Near", latitude=36.82)
        far = self.make_request(user=User.objects.create_user(
            username="third", password="password123", email="third@example.com"
        ), address="Far", latitude=36.85)
        self.client.force_login(self.user)

        response = self.client.get(reverse("waste:market"), {
            "latitude": "36.8065", "longitude": "10.1815"
        })

        self.assertEqual([row["request"] for row in response.context["rows"]], [near, far])

    def test_valid_claim_plans_request(self):
        request = self.make_request()
        planned_date = timezone.now() + timedelta(days=1)
        self.client.force_login(self.other_user)

        response = self.client.post(reverse("waste:claim", args=[request.pk]), {
            "planned_date": planned_date.strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.82",
            "longitude": "10.18",
        })

        self.assertRedirects(response, reverse("waste:my_collections"))
        request.refresh_from_db()
        self.assertEqual(request.status, Status.PLANNED)
        self.assertEqual(request.collector, self.other_user)
        self.assertEqual(request.collector_latitude, 36.82)
        self.assertEqual(request.logs.count(), 1)

    def test_claim_requires_position_and_future_date(self):
        request = self.make_request()
        self.client.force_login(self.other_user)
        claim_url = reverse("waste:claim", args=[request.pk])

        missing_position = self.client.post(claim_url, {
            "planned_date": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "", "longitude": "",
        })
        self.assertContains(missing_position, "Choisissez votre position sur la carte.")

        past_date = self.client.post(claim_url, {
            "planned_date": (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.82", "longitude": "10.18",
        })
        self.assertContains(past_date, "La date doit être dans le futur.")

    def test_user_cannot_claim_own_request(self):
        request = self.make_request()
        self.client.force_login(self.user)

        response = self.client.get(reverse("waste:claim", args=[request.pk]))

        self.assertEqual(response.status_code, 404)

    def test_claimed_request_is_no_longer_available(self):
        request = self.make_request()
        request.claim(self.other_user, 36.82, 10.18, timezone.now() + timedelta(days=1))
        third_user = User.objects.create_user(
            username="third", password="password123", email="third@example.com"
        )
        self.client.force_login(third_user)

        response = self.client.get(reverse("waste:claim", args=[request.pk]))

        self.assertEqual(response.status_code, 404)

    def test_release_clears_collection_and_is_authorized(self):
        request = self.make_request()
        request.claim(self.other_user, 36.82, 10.18, timezone.now() + timedelta(days=1))
        self.client.force_login(self.other_user)

        response = self.client.post(reverse("waste:release", args=[request.pk]))

        self.assertRedirects(response, reverse("waste:my_collections"))
        request.refresh_from_db()
        self.assertEqual(request.status, Status.REQUESTED)
        self.assertIsNone(request.collector)
        self.assertIsNone(request.planned_date)
        self.assertEqual(request.logs.count(), 2)

    def test_release_by_another_user_is_rejected(self):
        request = self.make_request()
        request.claim(self.other_user, 36.82, 10.18, timezone.now() + timedelta(days=1))
        self.client.force_login(self.user)

        response = self.client.post(reverse("waste:release", args=[request.pk]))

        self.assertEqual(response.status_code, 404)

    def test_my_collections_only_shows_current_user_collections(self):
        own_collection = self.make_request()
        own_collection.claim(self.other_user, 36.82, 10.18, timezone.now() + timedelta(days=1))
        third_user = User.objects.create_user(
            username="third", password="password123", email="third@example.com"
        )
        other_collection = self.make_request(user=third_user)
        other_collection.claim(self.user, 36.82, 10.18, timezone.now() + timedelta(days=1))
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("waste:my_collections"))

        self.assertEqual(list(response.context["collections"]), [own_collection])
