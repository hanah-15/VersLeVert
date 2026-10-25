from django.test import TestCase
from django.urls import reverse

from accounts.models import SponsorAccount, User
from sponsor.models import Offer


class RewardCatalogueFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="citizen",
            email="citizen@example.com",
            password="test-password",
        )
        clothing_user = User.objects.create_user(
            username="clothing",
            email="clothing@example.com",
            password="test-password",
        )
        technology_user = User.objects.create_user(
            username="technology",
            email="technology@example.com",
            password="test-password",
        )
        self.clothing_sponsor = SponsorAccount.objects.create(
            user=clothing_user,
            business_name="Atelier Local",
            activity=SponsorAccount.Activity.CLOTHING,
            description="Vêtements réutilisés",
            contact_email=clothing_user.email,
        )
        technology_sponsor = SponsorAccount.objects.create(
            user=technology_user,
            business_name="Green Tech",
            activity=SponsorAccount.Activity.TECHNOLOGY,
            description="Réparation numérique",
            contact_email=technology_user.email,
        )
        self.offer_high = Offer.objects.create(
            sponsor=self.clothing_sponsor,
            title="Hoodie",
            description="Un vêtement confortable",
            points_cost=80,
        )
        self.offer_low = Offer.objects.create(
            sponsor=self.clothing_sponsor,
            title="Sac réutilisable",
            description="Un accessoire pratique",
            points_cost=20,
        )
        Offer.objects.create(
            sponsor=technology_sponsor,
            title="Diagnostic numérique",
            description="Réparation d'appareil",
            points_cost=40,
        )
        self.client.force_login(self.user)

    def test_search_matches_offer_and_sponsor_fields(self):
        response = self.client.get(reverse("gamification:index"), {"q": "hoodie"})
        self.assertEqual(list(response.context["offers"]), [self.offer_high])

        response = self.client.get(reverse("gamification:index"), {"q": "Atelier"})
        self.assertEqual(
            set(response.context["offers"]),
            {self.offer_high, self.offer_low},
        )

    def test_activity_filter_and_points_sort(self):
        response = self.client.get(
            reverse("gamification:index"),
            {"activity": SponsorAccount.Activity.CLOTHING, "sort": "points_desc"},
        )
        self.assertEqual(
            list(response.context["offers"]),
            [self.offer_high, self.offer_low],
        )
