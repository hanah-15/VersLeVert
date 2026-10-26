from django.db import OperationalError
from django.http import Http404
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import path
from django.utils.functional import SimpleLazyObject

from config.urls import handler404, handler500, urlpatterns as site_urls
from core.views import page_not_found, server_error


def missing_record(request):
    raise Http404("Private record details")


def database_outage(request):
    raise OperationalError("Private database credentials")


# Failure routes exist only in this test URLconf, never on the deployed site.
urlpatterns = [
    *site_urls,
    path("_error-tests/missing/", missing_record),
    path("_error-tests/failure/", database_outage),
]


@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
class ErrorPageTests(SimpleTestCase):
    def test_unmatched_url_returns_custom_404_without_disclosing_request(self):
        response = self.client.get("/private-missing-address/?token=private-token")
        self.assertContains(response, "On a perdu le chemin.", status_code=404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, 'href="/"', status_code=404)
        self.assertNotContains(response, "private-missing-address", status_code=404)
        self.assertNotContains(response, "private-token", status_code=404)
        self.assertIn("no-store", response["Cache-Control"])

    def test_missing_record_uses_same_404_without_exception_details(self):
        response = self.client.get("/_error-tests/missing/")
        self.assertTemplateUsed(response, "404.html")
        self.assertNotContains(response, "Private record details", status_code=404)

    def test_unhandled_database_failure_returns_custom_500(self):
        client = Client(raise_request_exception=False)
        with self.assertLogs("django.request", level="ERROR"):
            response = client.get("/_error-tests/failure/")
        self.assertContains(response, "Une petite pause imprévue.", status_code=500)
        self.assertTemplateUsed(response, "500.html")
        self.assertContains(response, '>Réessayer</a>', status_code=500)
        self.assertNotContains(response, "Private database credentials", status_code=500)
        self.assertNotContains(response, "Traceback", status_code=500)
        self.assertIn("no-store", response["Cache-Control"])

    def test_error_handlers_work_when_session_user_cannot_be_loaded(self):
        def unavailable_user():
            raise OperationalError("The authentication database is down")

        request = RequestFactory().get("/missing/")
        request.user = SimpleLazyObject(unavailable_user)
        for handler, args, status in [
            (page_not_found, (Http404(),), 404),
            (server_error, (), 500),
        ]:
            with self.subTest(status=status):
                response = handler(request, *args)
                self.assertEqual(response.status_code, status)
                self.assertContains(response, 'lang="fr"', status_code=status)
                self.assertContains(response, '<style>', status_code=status)

    def test_head_retains_404_status_without_a_response_body(self):
        response = self.client.head("/missing/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"")
