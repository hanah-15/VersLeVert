from django.test import TestCase
from django.urls import reverse

from core.navigation import NAVIGATION

from .models import Notification, SponsorAccount, User


class SponsorAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="citizen",
            email="citizen@example.com",
            password="test-password-123",
        )

    def test_visitor_is_redirected_to_login(self):
        response = self.client.get(reverse("sponsor-dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('sponsor-dashboard')}")

    def test_normal_and_unapproved_users_are_forbidden(self):
        self.client.force_login(self.user)
        for status in [None, SponsorAccount.Status.PENDING, SponsorAccount.Status.REJECTED, SponsorAccount.Status.SUSPENDED]:
            if status:
                SponsorAccount.objects.update_or_create(
                    user=self.user,
                    defaults={
                        "business_name": "Entreprise",
                        "activity": "Recyclage",
                        "description": "Description",
                        "contact_email": self.user.email,
                        "status": status,
                    },
                )
            else:
                SponsorAccount.objects.filter(user=self.user).delete()
            self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 403)

    def test_approved_user_keeps_normal_access(self):
        SponsorAccount.objects.create(
            user=self.user,
            business_name="Entreprise",
            activity="Recyclage",
            description="Description",
            contact_email=self.user.email,
            status=SponsorAccount.Status.APPROVED,
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("sponsor-dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_registration_ignores_privilege_fields(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-citizen",
                "email": "new@example.com",
                "password1": "Strong-password-123",
                "password2": "Strong-password-123",
                "role": "ADMIN",
                "is_staff": "true",
                "is_sponsor": "true",
            },
        )
        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_sponsor)

    def test_authenticated_navigation_contains_profile_shell(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertContains(response, "Défis")
        self.assertContains(response, "Profil")
        self.assertContains(response, "Devenir sponsor")
        self.assertContains(response, 'method="post" action="/accounts/logout/"')

    def test_visitor_sees_landing_actions_only(self):
        response = self.client.get("/")
        self.assertContains(response, "Se connecter")
        self.assertContains(response, "S'inscrire")
        self.assertNotContains(response, "Notifications,")

    def test_navigation_config_urls_resolve(self):
        for item in NAVIGATION:
            self.assertTrue(reverse(item["url_name"]))

    def test_profile_pages_require_login_and_render(self):
        for url_name, args in [
            ("profile-overview", ()),
            ("profile-section", ("collector",)),
            ("profile-section", ("points",)),
            ("profile-section", ("proofs",)),
            ("profile-section", ("badges",)),
            ("profile-section", ("notifications",)),
            ("profile-section", ("sponsor",)),
            ("profile-section", ("security",)),
        ]:
            response = self.client.get(reverse(url_name, args=args))
            self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        for url_name, args in [
            ("profile-overview", ()),
            ("profile-section", ("collector",)),
            ("profile-section", ("notifications",)),
        ]:
            self.assertEqual(self.client.get(reverse(url_name, args=args)).status_code, 200)

    def test_role_specific_navigation_and_notification_counter(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get("/"), "Espace sponsor")
        self.assertNotContains(self.client.get("/"), "Administration")
        sponsor = SponsorAccount.objects.create(
            user=self.user,
            business_name="Entreprise",
            activity="Recyclage",
            description="Description",
            contact_email=self.user.email,
            status=SponsorAccount.Status.APPROVED,
        )
        self.assertContains(self.client.get("/"), "Espace sponsor")
        sponsor.status = SponsorAccount.Status.PENDING
        sponsor.save(update_fields=["status"])
        self.assertNotContains(self.client.get("/"), "Espace sponsor")
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.assertContains(self.client.get("/"), "Administration")
        Notification.objects.bulk_create(
            [Notification(user=self.user, message=f"Notification {index}") for index in range(10)]
        )
        response = self.client.get("/")
        self.assertContains(response, "9+")
