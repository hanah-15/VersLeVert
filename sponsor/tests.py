from django.test import TestCase
from django.urls import reverse

from accounts.models import SponsorAccount, User
from .models import Offer, RewardCode
from django.utils import timezone


class SponsorOwnershipTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="a", email="a@example.com", password="test-password-123")
        self.user_b = User.objects.create_user(username="b", email="b@example.com", password="test-password-123")
        self.sponsor_a = SponsorAccount.objects.create(
            user=self.user_a, business_name="A", activity=SponsorAccount.Activity.REPAIR_REUSE, description="A",
            contact_email=self.user_a.email, status=SponsorAccount.Status.APPROVED,
        )
        self.sponsor_b = SponsorAccount.objects.create(
            user=self.user_b, business_name="B", activity=SponsorAccount.Activity.REPAIR_REUSE, description="B",
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

    def test_redemption_requires_post_and_prevents_own_offer(self):
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.post(reverse("redeem-reward", args=[self.offer_a.pk])).status_code, 403)
        response = self.client.get(reverse("redeem-reward", args=[self.offer_b.pk]))
        self.assertRedirects(response, reverse("gamification:index"))
        self.assertFalse(RewardCode.objects.exists())
        self.assertRedirects(
            self.client.post(reverse("redeem-reward", args=[self.offer_b.pk])),
            reverse("gamification:my-codes"),
        )
        self.assertEqual(RewardCode.objects.get().redeemed_by, self.user_a)

    def test_suspension_removes_access(self):
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 200)
        self.sponsor_a.status = SponsorAccount.Status.SUSPENDED
        self.sponsor_a.save(update_fields=["status"])
        self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user_a.pk).exists())

    def test_deactivation_keeps_offer_and_codes_and_can_be_reactivated(self):
        code = RewardCode.objects.create(offer=self.offer_a, code='KEEP-ME', redeemed_by=self.user_b, redeemed_at=timezone.now())
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.delete(reverse('sponsor-offer-deactivate', args=[self.offer_a.pk])).status_code, 405)
        self.client.post(reverse('sponsor-offer-deactivate', args=[self.offer_a.pk]))
        self.offer_a.refresh_from_db()
        self.assertFalse(self.offer_a.active)
        self.assertTrue(RewardCode.objects.filter(pk=code.pk).exists())
        self.client.post(reverse('sponsor-offer-activate', args=[self.offer_a.pk]))
        self.offer_a.refresh_from_db()
        self.assertTrue(self.offer_a.active)

    def test_code_can_only_be_used_once_without_changing_exchange_date(self):
        acquired = timezone.now()
        code = RewardCode.objects.create(offer=self.offer_a, code='ONCE-ONLY', redeemed_by=self.user_b, redeemed_at=acquired)
        self.assertFalse(code.is_used)
        self.client.force_login(self.user_a)
        self.client.post(reverse('sponsor-code-check'), {'code_value': 'once-only'})
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertEqual(code.redeemed_at, acquired)
        used = code.used_at
        self.client.post(reverse('sponsor-code-check'), {'code_value': 'ONCE-ONLY'})
        code.refresh_from_db()
        self.assertEqual(code.used_at, used)

    def test_other_sponsor_cannot_validate_or_list_codes(self):
        code = RewardCode.objects.create(offer=self.offer_b, code='PRIVATE-CODE', redeemed_by=self.user_a, redeemed_at=timezone.now())
        self.client.force_login(self.user_a)
        self.client.post(reverse('sponsor-code-check'), {'code_value': code.code})
        code.refresh_from_db()
        self.assertIsNone(code.used_at)
        self.assertNotContains(self.client.get(reverse('sponsor-codes')), code.code)

    def test_unapproved_sponsor_offers_cannot_be_exchanged(self):
        self.sponsor_b.status = SponsorAccount.Status.SUSPENDED
        self.sponsor_b.save(update_fields=['status'])
        self.client.force_login(self.user_a)
        self.assertNotContains(self.client.get(reverse('gamification:index')), 'Offre B')
        self.assertEqual(self.client.post(reverse('redeem-reward', args=[self.offer_b.pk])).status_code, 404)
