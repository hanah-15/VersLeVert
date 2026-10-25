from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from accounts.models import SponsorAccount
from challenges.models import Challenge, ChallengeMilestone, ChallengeParticipation
from events.models import Event, EventRegistration
from sponsor.models import Offer, RewardCode
from waste.models import EmissionFactor, Status, WasteRequest, WasteType

from .models import Badge, EcoProof, ImpactFactor, PointsTransaction, UserBadge
from .services import PointsService, award_points


@override_settings(GEMINI_API_KEY="", GROQ_API_KEY="")
class SharedPointsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.user = users.objects.create_user(username="points-citizen", email="points@example.test")
        cls.staff = users.objects.create_user(username="points-staff", email="points-staff@example.test", is_staff=True)
        cls.partner_user = users.objects.create_user(username="points-partner", email="points-partner@example.test")
        cls.partner = SponsorAccount.objects.create(
            user=cls.partner_user, business_name="Test partner", activity=SponsorAccount.Activity.REPAIR_REUSE,
            status=SponsorAccount.Status.APPROVED, contact_email=cls.partner_user.email,
        )
        cls.offer = Offer.objects.create(sponsor=cls.partner, title="Repair voucher", points_cost=80)

    def test_waste_challenges_events_and_proofs_share_a_spendable_balance(self):
        Badge.objects.create(
            code="first-100", name="First 100 points", criteria_type=Badge.CriteriaType.TOTAL_POINTS,
            threshold=100,
        )
        # Module-owned reward amounts must not be multiplied by these factors again.
        ImpactFactor.objects.create(action_type="EVENT_PARTICIPANT", label="Events", unit="count", points_per_unit=25)
        ImpactFactor.objects.create(action_type="CHALLENGE_BONUS", label="Challenges", unit="count", points_per_unit=10)
        EmissionFactor.objects.update_or_create(waste_type=WasteType.PLASTIC, defaults={"kg_co2_per_kg": "1.8"})
        request = WasteRequest.objects.create(
            user=self.user, collector=self.partner_user, waste_type=WasteType.PLASTIC,
            estimated_weight=2, address="Tunis", latitude=36.8, longitude=10.1, status=Status.PLANNED,
        )
        request.confirm(Decimal("1.50"), self.partner_user)
        waste_tx = PointsTransaction.objects.get(source_type="waste", source_id=request.pk)
        self.assertEqual(waste_tx.points, request.points_awarded)
        self.assertEqual(waste_tx.points, 23)  # Same ROUND_HALF_UP rule as waste.
        self.assertEqual(waste_tx.quantity, Decimal("1.50"))
        self.assertEqual(waste_tx.action_type, "WASTE_PLASTIC")
        request._award_points()

        challenge = Challenge.objects.create(
            title="Walk 10 km", goal_value=10, unit="km", challenge_type=Challenge.Type.POINTS,
            points_reward=50, created_by=self.staff,
        )
        ChallengeMilestone.objects.create(challenge=challenge, title="Halfway", threshold=50, reward_points=5)
        participation = ChallengeParticipation.objects.create(user=self.user, challenge=challenge)
        participation.add_progress(Decimal("10"))
        participation.add_progress(Decimal("1"))

        event = Event.objects.create(
            organizer=self.staff, title="Park cleanup", location="Tunis", objective="Clean the park",
            date=timezone.now() - timedelta(days=1), status=Event.Status.PUBLISHED, points_reward=40,
        )
        EventRegistration.objects.create(event=event, user=self.user, present=True)
        event.close_and_award_points(by_user=self.staff)
        event.close_and_award_points(by_user=self.staff)
        self.assertEqual(PointsService.balance(self.user), 118)
        self.assertEqual(PointsTransaction.objects.filter(user=self.user).count(), 4)
        self.assertEqual(UserBadge.objects.filter(user=self.user).count(), 1)

        ImpactFactor.objects.create(action_type="OTHER", label="Other proof", unit="proof", points_per_unit=20)
        proof = EcoProof.objects.create(
            user=self.user, proof_type=EcoProof.ProofType.OTHER, file="test-proof.pdf",
            file_hash="a" * 64, proof_date=timezone.localdate(),
        )
        self.client.force_login(self.staff)
        for _ in range(2):
            response = self.client.post(reverse("gamification:admin-proof-review", args=[proof.pk]), {"action": "approve"})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(PointsService.balance(self.user), 138)

        self.client.force_login(self.user)
        response = self.client.post(reverse("redeem-reward", args=[self.offer.pk]))
        self.assertRedirects(response, reverse("gamification:my-codes"))
        self.assertEqual(PointsService.balance(self.user), 58)
        self.assertEqual(RewardCode.objects.filter(redeemed_by=self.user).count(), 1)
        self.client.post(reverse("redeem-reward", args=[self.offer.pk]))
        self.assertEqual(RewardCode.objects.filter(redeemed_by=self.user).count(), 1)
        self.assertEqual(PointsService.balance(self.user), 58)
        history = self.client.get(reverse("gamification:points-history"))
        self.assertContains(history, "Park cleanup")
        self.assertContains(history, "+40 pts")
        self.assertContains(history, "-80 pts")

    def test_duplicate_source_remains_safe_when_description_changes(self):
        award_points(self.user, "event", 123, 50, description="Original title")
        self.assertIsNone(award_points(self.user, "event", 123, 50, description="Renamed event"))
        # A duplicate must leave the enclosing TestCase transaction usable.
        award_points(self.user, "challenge", 123, 10)
        self.assertEqual(PointsService.balance(self.user), 60)

    def test_zero_rewards_and_negative_debits_do_not_create_points(self):
        self.assertIsNone(award_points(self.user, "event", 1, 0))
        self.assertIsNone(PointsService.credit(self.user, "OTHER", quantity=0))
        with self.assertRaises(ValueError):
            PointsService.debit(self.user, -50)
        self.assertEqual(PointsService.balance(self.user), 0)

    def test_staff_reward_pages_and_shared_quick_actions_render(self):
        self.client.force_login(self.staff)
        for name in ("gamification:admin-proof-queue", "gamification:admin-impact-factors", "gamification:admin-badges",
                     "admin_dashboard:dashboard", "admin_dashboard:users_list", "admin_dashboard:sponsors_list"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.client.force_login(self.user)
        for name in ("gamification:my-proofs", "gamification:proof-submit", "gamification:badges", "gamification:my-codes"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertRedirects(self.client.get(reverse("proof-create")), reverse("gamification:proof-submit"))

    def test_backoffice_links_open_delivered_modules_and_require_staff(self):
        destinations = {
            "challenges": "challenges:admin-stats", "events": "events:mine",
            "places": "places:moderation", "waste": "waste:index",
            "gamification": "gamification:admin-proof-queue",
        }
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin_dashboard:module_challenges")).status_code, 403)
        self.client.force_login(self.staff)
        for module, destination in destinations.items():
            with self.subTest(module=module):
                self.assertRedirects(self.client.get(reverse(f"admin_dashboard:module_{module}")), reverse(destination))


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentPointsTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="parallel-points", email="parallel@example.test")

    def run_together(self, operation):
        barrier = Barrier(2)

        def worker(index):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                return operation(user, index)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_simultaneous_credits_keep_both_amounts(self):
        self.run_together(lambda user, index: award_points(user, "event", index + 1, 30))
        self.assertEqual(PointsService.balance(self.user), 60)

    def test_simultaneous_duplicate_is_credited_once(self):
        self.run_together(lambda user, index: award_points(user, "event", 1, 30))
        self.assertEqual(PointsService.balance(self.user), 30)
        self.assertEqual(PointsTransaction.objects.count(), 1)

    def test_simultaneous_debits_cannot_spend_the_same_balance(self):
        award_points(self.user, "event", 1, 100)
        results = self.run_together(lambda user, index: PointsService.debit(user, 80, source_type="offer", source_id=index + 1))
        self.assertEqual(sum(tx is not None for tx in results), 1)
        self.assertEqual(PointsService.balance(self.user), 20)
