from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.utils import distance_km

from .forms import OfferForm, WasteRequestForm
from .models import (
    CollectionOffer,
    EmissionFactor,
    Status,
    WasteRequest,
    WasteStatusLog,
    WasteType,
)
from .services import user_impact
from waste.services import total_impact
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

    def test_requests_are_paginated(self):
        for index in range(7):
            self.make_request(address=f"Adresse {index}")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("waste:index"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["requests"]), 3)

    def test_pagination_controls_are_visible_on_single_page(self):
        self.make_request()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("waste:index"))
        self.assertContains(response, "Page 1 sur 1")
        self.assertContains(response, "Précédent")
        self.assertContains(response, "Suivant")

    def test_owner_can_edit_requested_request_but_other_user_cannot(self):
        request = self.make_request()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("waste:edit", args=[request.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("waste:edit", args=[request.pk]),
            {
                "waste_type": WasteType.PLASTIC,
                "estimated_weight": "3.00",
                "address": "Nouvelle adresse",
                "latitude": "36.8",
                "longitude": "10.1",
            },
        )
        self.assertRedirects(response, reverse("waste:detail", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.address, "Nouvelle adresse")
        self.client.force_login(self.collector)
        self.assertEqual(
            self.client.get(reverse("waste:edit", args=[request.pk])).status_code,
            404,
        )

    def test_requested_request_can_be_deleted_only_by_owner(self):
        request = self.make_request()
        self.client.force_login(self.collector)
        self.assertEqual(
            self.client.post(reverse("waste:delete", args=[request.pk])).status_code,
            404,
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("waste:delete", args=[request.pk]))
        self.assertRedirects(response, reverse("waste:index"))
        self.assertFalse(WasteRequest.objects.filter(pk=request.pk).exists())

    def test_total_impact_uses_confirmed_requests_once(self):
        self.make_request(
            status=Status.CONFIRMED,
            confirmed_weight=Decimal("2"),
            co2_avoided=Decimal("3.000"),
            points_awarded=20,
        )
        self.make_request(
            status=Status.REQUESTED,
            confirmed_weight=None,
            co2_avoided=None,
            points_awarded=None,
        )
        self.assertEqual(total_impact()["co2"], Decimal("3.000"))
        self.assertEqual(total_impact()["points"], 20)
        home = self.client.get(reverse("home"))
        self.assertContains(home, "kg de CO₂ évités")
        self.assertContains(home, "points gagnés")

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

    def test_market_shows_address_and_detail_hides_collector_position(self):
        request = self.make_request()
        offer = self.make_offer(request)
        self.client.force_login(self.collector)
        market = self.client.get(reverse("waste:market"))
        self.assertContains(market, request.address)
        self.client.force_login(self.owner)
        detail = self.client.get(reverse("waste:detail", args=[request.pk]))
        self.assertContains(detail, "1.5")
        self.assertNotContains(detail, str(offer.latitude))
        self.assertNotContains(detail, str(offer.longitude))

    def test_market_uses_existing_offer_position_for_distance(self):
        request = self.make_request()
        self.make_offer(request)
        self.client.force_login(self.collector)
        market = self.client.get(reverse("waste:market"))
        self.assertContains(market, "1.5 km de vous")

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
    

class ConfirmViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("own2", "own2@test.com", "Pass12345!")
        self.collector = User.objects.create_user("col2", "col2@test.com", "Pass12345!")
        EmissionFactor.objects.update_or_create(
            waste_type="plastic", defaults={"kg_co2_per_kg": Decimal("1.5")})
        self.req = WasteRequest.objects.create(
            user=self.owner, collector=self.collector, waste_type="plastic",
            estimated_weight=Decimal("2"), address="x", status=Status.PLANNED)
        self.url = reverse("waste:confirm", args=[self.req.pk])

    def test_login_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_collector_sees_the_page(self):
        self.client.force_login(self.collector)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_owner_cannot_open_the_page(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_stranger_cannot_open_the_page(self):
        stranger = User.objects.create_user("str", "str@test.com", "Pass12345!")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_valid_post_confirms(self):
        self.client.force_login(self.collector)
        response = self.client.post(self.url, {"confirmed_weight": "1.8"})
        self.assertRedirects(response, reverse("waste:my_offers"))
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Status.CONFIRMED)
        self.assertEqual(self.req.points_awarded, 27)
        self.assertEqual(self.req.co2_avoided, Decimal("2.700"))

    def test_too_heavy_is_rejected(self):
        self.client.force_login(self.collector)
        response = self.client.post(self.url, {"confirmed_weight": "6.5"})
        self.assertEqual(response.status_code, 200)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Status.PLANNED)

    def test_zero_weight_is_rejected(self):
        self.client.force_login(self.collector)
        self.client.post(self.url, {"confirmed_weight": "0"})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Status.PLANNED)

    def test_second_confirmation_is_blocked(self):
        self.client.force_login(self.collector)
        self.client.post(self.url, {"confirmed_weight": "1.8"})
        response = self.client.post(self.url, {"confirmed_weight": "1.9"})
        self.assertEqual(response.status_code, 404)
        self.req.refresh_from_db()
        self.assertEqual(self.req.confirmed_weight, Decimal("1.80"))

    def test_detail_shows_results_to_the_owner(self):
        self.client.force_login(self.collector)
        self.client.post(self.url, {"confirmed_weight": "1.8"})
        self.client.force_login(self.owner)
        response = self.client.get(reverse("waste:detail", args=[self.req.pk]))
        self.assertContains(response, "Points : 27")


class ImpactTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("impact-owner", "impact-owner@test.com", "Pass12345!")
        self.collector = User.objects.create_user(
            "impact-collector", "impact-collector@test.com", "Pass12345!"
        )
        self.inactive = User.objects.create_user(
            "impact-inactive", "impact-inactive@test.com", "Pass12345!"
        )

    def make_request(self, **overrides):
        values = {
            "user": self.owner,
            "collector": self.collector,
            "waste_type": WasteType.ORGANIC,
            "estimated_weight": Decimal("2"),
            "confirmed_weight": Decimal("1.5"),
            "co2_avoided": Decimal("1.500"),
            "address": "Adresse",
            "status": Status.CONFIRMED,
        }
        values.update(overrides)
        return WasteRequest.objects.create(**values)

    def test_only_confirmed_requests_count(self):
        self.make_request()
        self.make_request(status=Status.COLLECTED, confirmed_weight=Decimal("4"), co2_avoided=Decimal("4"))

        impact = user_impact(self.owner)

        self.assertEqual(impact["declared"], {"co2": Decimal("1.500"), "kg": Decimal("1.5"), "count": 1})

    def test_collector_has_separate_totals(self):
        self.make_request()
        self.make_request(user=self.collector, confirmed_weight=Decimal("2"), co2_avoided=Decimal("2.000"))

        impact = user_impact(self.collector)

        self.assertEqual(impact["declared"], {"co2": Decimal("2.000"), "kg": Decimal("2"), "count": 1})
        self.assertEqual(impact["collected"], {"co2": Decimal("3.500"), "kg": Decimal("3.5"), "count": 2})

    def test_user_without_activity_has_zero_totals(self):
        impact = user_impact(self.inactive)

        self.assertEqual(impact, {
            "declared": {"co2": Decimal("0"), "kg": Decimal("0"), "count": 0},
            "collected": {"co2": Decimal("0"), "kg": Decimal("0"), "count": 0},
        })