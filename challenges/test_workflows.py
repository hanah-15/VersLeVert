from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Notification
from .models import (
    Challenge,
    ChallengeMilestone,
    ChallengeMilestoneAchievement,
    ChallengeParticipation,
    ChallengeReminder,
)


class ChallengeWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.user = users.objects.create_user(
            username="challenge-user", email="challenge-user@example.test"
        )
        cls.other = users.objects.create_user(
            username="other-challenger", email="other-challenger@example.test"
        )
        cls.staff = users.objects.create_user(
            username="challenge-staff", email="challenge-staff@example.test", is_staff=True
        )
        cls.challenge = Challenge.objects.create(
            title="Cycle thirty kilometres", goal_value=30, unit="km",
            challenge_type=Challenge.Type.POINTS, points_reward=50, created_by=cls.staff,
        )

    def test_module_requires_login_and_limits_staff_pages(self):
        for name in ("index", "mine", "dashboard", "leaderboard", "recommendations", "personal-create"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"challenges:{name}"))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        self.client.force_login(self.user)
        for name in ("admin-create", "admin-stats"):
            self.assertEqual(self.client.get(reverse(f"challenges:{name}")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("challenges:close", args=[self.challenge.pk])).status_code, 403
        )
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, Challenge.Status.ACTIVE)

    def test_module_pages_render_with_real_data(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("challenges:index")), self.challenge.title)
        self.assertContains(
            self.client.get(reverse("challenges:detail", args=[self.challenge.pk])), self.challenge.title
        )
        for name in ("mine", "dashboard", "leaderboard", "recommendations", "personal-create"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"challenges:{name}")).status_code, 200)
        self.client.force_login(self.staff)
        for name in ("admin-create", "admin-stats"):
            self.assertEqual(self.client.get(reverse(f"challenges:{name}")).status_code, 200)

    def test_shared_quick_action_creates_a_personal_challenge_without_points(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("personal-challenge-create"), {
            "title": "My walking goal", "goal_value": "10", "unit": "km",
            "challenge_type": "points", "points_reward": 999,
        })
        challenge = Challenge.objects.get(title="My walking goal")
        self.assertRedirects(response, challenge.get_absolute_url())
        self.assertEqual(challenge.created_by, self.user)
        self.assertEqual(challenge.challenge_type, Challenge.Type.PERSONAL)
        self.assertEqual(challenge.points_reward, 0)
        self.assertTrue(ChallengeParticipation.objects.filter(challenge=challenge, user=self.user).exists())

    def test_joining_is_post_only_and_duplicates_or_expired_challenges_are_rejected(self):
        self.client.force_login(self.user)
        join_url = reverse("challenges:join", args=[self.challenge.pk])
        self.assertEqual(self.client.get(join_url).status_code, 405)
        self.client.post(join_url)
        self.client.post(join_url)
        self.assertEqual(self.challenge.participations.filter(user=self.user).count(), 1)
        self.challenge.end_date = timezone.now().date() - timedelta(days=1)
        self.challenge.save()
        self.client.force_login(self.other)
        self.client.post(join_url)
        self.assertFalse(self.challenge.participations.filter(user=self.other).exists())

    @patch("gamification.services.award_points", autospec=True)
    def test_progress_completion_and_milestones_call_the_shared_points_service_once(self, award_points):
        participation = ChallengeParticipation.objects.create(challenge=self.challenge, user=self.user)
        milestone = ChallengeMilestone.objects.create(
            challenge=self.challenge, title="Halfway", threshold=50, reward_points=0,
        )
        self.client.force_login(self.user)
        progress_url = reverse("challenges:add-progress", args=[self.challenge.pk])
        for value in ("15", "15", "1"):
            self.assertEqual(self.client.post(progress_url, {"value": value}).status_code, 302)
        participation.refresh_from_db()
        self.assertEqual(participation.progress_value, Decimal("31"))
        self.assertTrue(participation.points_awarded)
        self.assertIsNotNone(participation.completed_at)
        self.assertEqual(participation.progress_entries.count(), 3)
        self.assertEqual(ChallengeMilestoneAchievement.objects.filter(user=self.user, milestone=milestone).count(), 1)
        award_points.assert_called_once()
        self.assertEqual(award_points.call_args.kwargs["source_type"], "challenge")
        self.assertEqual(award_points.call_args.kwargs["source_id"], self.challenge.pk)
        self.assertEqual(award_points.call_args.kwargs["base_points"], 50)

    def test_api_creates_personal_challenges_and_protects_other_users_progress(self):
        api = APIClient()
        self.assertIn(api.get(reverse("challenges:api-list")).status_code, (401, 403))
        api.force_authenticate(self.user)
        response = api.post(reverse("challenges:api-list"), {
            "title": "API personal goal", "goal_value": "20", "unit": "km",
            "challenge_type": "points", "points_reward": 999,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        challenge = Challenge.objects.get(pk=response.data["id"])
        self.assertEqual(challenge.challenge_type, Challenge.Type.PERSONAL)
        self.assertEqual(challenge.points_reward, 0)
        participation = challenge.participations.get(user=self.user)
        progress_url = reverse("challenges:api-add-progress", args=[participation.pk])
        self.assertEqual(api.post(progress_url, {"value": "-1"}, format="json").status_code, 400)
        api.force_authenticate(self.other)
        self.assertEqual(api.post(progress_url, {"value": "5"}, format="json").status_code, 404)
        participation.refresh_from_db()
        self.assertEqual(participation.progress_value, Decimal("0"))
        api.force_authenticate(self.user)
        self.assertEqual(api.post(progress_url, {"value": "5"}, format="json").status_code, 200)
        participation.refresh_from_db()
        self.assertEqual(participation.progress_value, Decimal("5"))

    def test_reminders_use_shared_notifications_and_are_not_sent_twice(self):
        ChallengeParticipation.objects.create(challenge=self.challenge, user=self.user)
        ChallengeReminder.objects.create(user=self.user, challenge=self.challenge)
        for _ in range(2):
            call_command("send_challenge_reminders", stdout=StringIO())
        self.assertEqual(Notification.objects.filter(user=self.user, message__startswith="Rappel").count(), 1)

    @override_settings(GROQ_API_KEY="")
    def test_recommendations_handle_missing_configuration_without_network_calls(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("challenges:recommendations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GROQ_API_KEY")
        with patch("challenges.views.recommend_challenges", return_value="Try cycling") as recommend:
            response = self.client.post(reverse("challenges:recommendations"))
        self.assertContains(response, "Try cycling")
        self.assertEqual([item.pk for item in recommend.call_args.args[1]], [self.challenge.pk])
