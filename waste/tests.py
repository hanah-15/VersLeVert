from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.utils import distance_km

from .forms import OfferForm, WasteRequestForm
from .models import CollectionOffer, Status, WasteRequest, WasteStatusLog, WasteType


User = get_user_model()


class WasteTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", password="password123", email="owner@example.com"
        )
        self.collector = User.objects.create_user(
            username="collector", password="password123", email="collector@example.com"
        )
        self.other = User.objects.create_user(
            username="other", password="password123", email="other@example.com"
        )

    def make_request(self, user=None, **overrides):
        data = {
            "user": user or self.owner,
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": Decimal("2.50"),
            "address": "Adresse exacte à Tunis",
            "latitude": 36.8065,
            "longitude": 10.1815,
        }
        data.update(overrides)
        return WasteRequest.objects.create(**data)

    def make_offer(self, request, collector=None, **overrides):
        data = {
            "waste_request": request,
            "collector": collector or self.collector,
            "latitude": 36.82,
            "longitude": 10.18,
            "proposed_date": timezone.now() + timedelta(days=1),
            "message": "Je peux passer demain.",
        }
        data.update(overrides)
        return CollectionOffer.objects.create(**data)

    def test_login_required_and_private_index(self):
        response = self.client.get(reverse("waste:index"))
        self.assertEqual(response.status_code, 302)
        self.make_request()
        self.make_request(user=self.collector)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("waste:index"))
        self.assertEqual(response.context["requests"].count(), 1)

    def test_request_form_validations(self):
        valid = {
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": "2.5",
            "address": "Tunis",
            "latitude": "36.8065",
            "longitude": "10.1815",
        }
        form = WasteRequestForm(data=valid)
        self.assertTrue(form.is_valid())
        form = WasteRequestForm(data={**valid, "address": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("Ce champ est obligatoire.", form.errors["address"])
        form = WasteRequestForm(data={**valid, "estimated_weight": "0"})
        self.assertFalse(form.is_valid())
        form = WasteRequestForm(data={**valid, "latitude": "", "longitude": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("Choisissez la position sur la carte.", form.non_field_errors())

    def test_valid_offer_does_not_change_request(self):
        request = self.make_request()
        self.client.force_login(self.collector)
        response = self.client.post(reverse("waste:offer", args=[request.pk]), {
            "planned_date": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.82",
            "longitude": "10.18",
            "message": "Disponible demain.",
        })
        self.assertRedirects(response, reverse("waste:my_offers"))
        request.refresh_from_db()
        self.assertEqual(request.status, Status.REQUESTED)
        self.assertIsNone(request.collector)
        self.assertEqual(CollectionOffer.objects.get().status, CollectionOffer.Status.PENDING)

    def test_offer_requires_position_and_future_date(self):
        form = OfferForm(data={
            "planned_date": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "", "longitude": "", "message": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Choisissez votre position sur la carte.", form.non_field_errors())
        form = OfferForm(data={
            "planned_date": (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.82", "longitude": "10.18", "message": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("La date doit être dans le futur.", form.errors["planned_date"])

    def test_cannot_offer_on_own_request(self):
        request = self.make_request()
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("waste:offer", args=[request.pk])).status_code, 404
        )

    def test_withdraw_then_reoffer_reuses_offer(self):
        request = self.make_request()
        offer = self.make_offer(request)
        offer.withdraw(self.collector)
        self.client.force_login(self.collector)
        self.client.post(reverse("waste:offer", args=[request.pk]), {
            "planned_date": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.83", "longitude": "10.19", "message": "Nouvelle date",
        })
        self.assertEqual(CollectionOffer.objects.count(), 1)
        offer.refresh_from_db()
        self.assertEqual(offer.status, CollectionOffer.Status.PENDING)
        self.assertEqual(offer.message, "Nouvelle date")

    def test_declined_offer_cannot_be_reoffered(self):
        request = self.make_request()
        offer = self.make_offer(request)
        request.decline_offer(offer, self.owner, "Pas disponible.")
        self.client.force_login(self.collector)
        response = self.client.post(reverse("waste:offer", args=[request.pk]), {
            "planned_date": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "latitude": "36.83", "longitude": "10.19",
        })
        self.assertRedirects(response, reverse("waste:market"))

    def test_accept_declines_other_pending_offers(self):
        request = self.make_request()
        first = self.make_offer(request)
        second_user = User.objects.create_user(
            username="second", password="password123", email="second@example.com"
        )
        second = self.make_offer(request, collector=second_user)
        request.accept_offer(first, self.owner)
        request.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(request.status, Status.PLANNED)
        self.assertEqual(request.collector, self.collector)
        self.assertEqual(first.status, CollectionOffer.Status.ACCEPTED)
        self.assertEqual(second.status, CollectionOffer.Status.DECLINED)
        self.assertEqual(second.decision_note, "Une autre proposition a été acceptée.")
        self.assertEqual(WasteStatusLog.objects.filter(request=request).count(), 1)

    def test_only_owner_can_accept_decline_or_view_detail(self):
        request = self.make_request()
        offer = self.make_offer(request)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("waste:detail", args=[request.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("waste:offer_accept", args=[offer.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse("waste:offer_decline", args=[offer.pk])).status_code, 404
        )

    def test_release_accepted_offer_reopens_request(self):
        request = self.make_request()
        offer = self.make_offer(request)
        request.accept_offer(offer, self.owner)
        offer.refresh_from_db()
        offer.release(self.collector)
        request.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(request.status, Status.REQUESTED)
        self.assertIsNone(request.collector)
        self.assertEqual(offer.status, CollectionOffer.Status.WITHDRAWN)
        self.assertEqual(WasteStatusLog.objects.filter(request=request).count(), 2)

    def test_cancel_declines_pending_offers(self):
        request = self.make_request()
        offer = self.make_offer(request)
        request.cancel_request(self.owner)
        request.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(request.status, Status.CANCELLED)
        self.assertEqual(offer.status, CollectionOffer.Status.DECLINED)
        self.assertEqual(offer.decision_note, "La demande a été annulée.")

    def test_market_hides_address_and_detail_hides_collector_position(self):
        request = self.make_request()
        offer = self.make_offer(request)
        self.client.force_login(self.collector)
        market = self.client.get(reverse("waste:market"))
        self.assertNotContains(market, request.address)
        self.client.force_login(self.owner)
        detail = self.client.get(reverse("waste:detail", args=[request.pk]))
        self.assertContains(detail, "1.5")
        self.assertNotContains(detail, str(offer.latitude))
        self.assertNotContains(detail, str(offer.longitude))

    def test_my_offers_shows_address_only_when_accepted(self):
        request = self.make_request()
        offer = self.make_offer(request)
        self.client.force_login(self.collector)
        pending = self.client.get(reverse("waste:my_offers"))
        self.assertNotContains(pending, request.address)
        request.accept_offer(offer, self.owner)
        accepted = self.client.get(reverse("waste:my_offers"))
        self.assertContains(accepted, request.address)

    def test_post_only_actions_reject_get(self):
        request = self.make_request()
        offer = self.make_offer(request)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("waste:offer_accept", args=[offer.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("waste:offer_decline", args=[offer.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("waste:cancel", args=[request.pk])).status_code, 405)
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(reverse("waste:offer_withdraw", args=[offer.pk])).status_code, 405)

    def test_distance_is_plausible(self):
        self.assertAlmostEqual(
            distance_km(36.8065, 10.1815, 36.868, 10.1815), 6.8, delta=0.5
        )
