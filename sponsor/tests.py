from django.test import TestCase
from django.urls import reverse

from accounts.models import SponsorAccount, User
from .models import Offer, RewardCode


class SponsorOwnershipTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="a", email="a@example.com", password="test-password-123")
        self.user_b = User.objects.create_user(username="b", email="b@example.com", password="test-password-123")
        self.sponsor_a = SponsorAccount.objects.create(
            user=self.user_a, business_name="A", activity="Recyclage", description="A",
            contact_email=self.user_a.email, status=SponsorAccount.Status.APPROVED,
        )
        self.sponsor_b = SponsorAccount.objects.create(
            user=self.user_b, business_name="B", activity="Recyclage", description="B",
            contact_email=self.user_b.email, status=SponsorAccount.Status.APPROVED,
        )
        self.offer_a = Offer.objects.create(sponsor=self.sponsor_a, title="Offre A", description="A")
        self.offer_b = Offer.objects.create(sponsor=self.sponsor_b, title="Offre B", description="B")

    def test_sponsor_cannot_see_or_edit_another_sponsors_offer(self):
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("sponsor-offer-edit", args=[self.offer_b.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("sponsor-shop")), "Offre B")
        stats = self.client.get(reverse("sponsor-stats"))
        self.assertContains(stats, "1")

    def test_sponsor_cannot_redeem_own_offer_but_can_redeem_other_offer(self):
        own_code = RewardCode.objects.create(offer=self.offer_a, code="OWN")
        other_code = RewardCode.objects.create(offer=self.offer_b, code="OTHER")
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("redeem-reward", args=[own_code.pk])).status_code, 403)
        response = self.client.get(reverse("redeem-reward", args=[other_code.pk]))
        self.assertRedirects(response, reverse("home"))
        other_code.refresh_from_db()
        self.assertEqual(other_code.redeemed_by, self.user_a)

    def test_suspension_removes_access(self):
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 200)
        self.sponsor_a.status = SponsorAccount.Status.SUSPENDED
        self.sponsor_a.save(update_fields=["status"])
        self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user_a.pk).exists())
