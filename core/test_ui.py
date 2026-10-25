from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import SponsorAccount
from sponsor.models import Offer


class PresentationContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ui-user", email="ui@example.test", password="Test-Password-2026!"
        )
        cls.partner_user = get_user_model().objects.create_user(
            username="ui-partner", email="partner-ui@example.test", password="Test-Password-2026!"
        )
        cls.partner = SponsorAccount.objects.create(
            user=cls.partner_user, business_name="Entreprise test", activity="Commerce",
            description="Test", contact_email="partner-ui@example.test",
            status=SponsorAccount.Status.APPROVED,
        )
        cls.offer = Offer.objects.create(
            sponsor=cls.partner, title="Offre test", description="Description", points_cost=20
        )

    def test_public_pages_and_authentication_fields_render(self):
        for name in ("home", "login", "signup"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        login = self.client.get(reverse("login"), {"next": "/places/"})
        self.assertContains(login, 'name="username"')
        self.assertContains(login, 'name="password"')
        self.assertContains(login, 'name="next" value="/places/"')
        self.assertContains(login, 'name="csrfmiddlewaretoken"')
        signup = self.client.get(reverse("signup"))
        for name in ("username", "email", "password1", "password2"):
            self.assertContains(signup, f'name="{name}"')
        self.assertContains(signup, 'aria-describedby="id_password1_helptext"')
        self.assertContains(signup, 'id="id_password1_helptext"')

    def test_login_validation_and_redirect_are_preserved(self):
        response = self.client.post(reverse("login"), {"username": self.user.email, "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        response = self.client.post(reverse("login"), {
            "username": self.user.email, "password": "Test-Password-2026!", "next": "/places/"
        })
        self.assertRedirects(response, "/places/")

    def test_user_pages_and_password_form_render(self):
        self.client.force_login(self.user)
        for url in ("/", "/places/", "/places/recommandations/", "/challenges/", "/events/",
                    "/rewards/", "/profil/", "/profil/securite/mot-de-passe/", "/notifications/",
                    "/sponsor/apply/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, follow=True).status_code, 200)
        response = self.client.get(reverse("password_change"))
        for name in ("old_password", "new_password1", "new_password2"):
            self.assertContains(response, f'name="{name}"')

    def test_partner_forms_and_confirmation_render(self):
        self.client.force_login(self.partner_user)
        for name in ("sponsor-dashboard", "sponsor-profile", "sponsor-shop", "sponsor-stats", "sponsor-offer-new"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for name in ("sponsor-offer-edit", "sponsor-offer-deactivate"):
            self.assertEqual(self.client.get(reverse(name, args=[self.offer.pk])).status_code, 200)
        self.assertTrue(Offer.objects.filter(pk=self.offer.pk).exists())

    def test_waste_keeps_original_presentation(self):
        self.client.force_login(self.user)
        for name in ("waste:index", "waste:create", "waste:market", "waste:my_offers"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "base.html")
                self.assertNotContains(response, 'class="site-body')
