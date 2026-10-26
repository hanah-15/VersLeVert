from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class DeploymentReadinessTests(TestCase):
    def test_readiness_works_without_login_and_is_not_cached(self):
        response = self.client.get(reverse("healthcheck"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-store", response["Cache-Control"])

    @patch("core.views.connection.cursor", side_effect=OperationalError("private database detail"))
    def test_database_outage_is_unhealthy_without_exposing_details(self, cursor):
        response = self.client.get(reverse("healthcheck"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "private database detail", status_code=503)

    def test_readiness_does_not_accept_writes(self):
        self.assertEqual(self.client.post(reverse("healthcheck")).status_code, 405)
