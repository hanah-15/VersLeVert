from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import EventProposalForm
from .models import Event, EventRegistration

User = get_user_model()


@override_settings(GEMINI_API_KEY="")
class EventM3Tests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user(
            username="citizen_oussema",
            email="citizen@example.com",
            password="Password123!",
            first_name="Oussema",
            last_name="Ben Ali",
        )
        self.participant1 = User.objects.create_user(
            username="participant_1",
            email="p1@example.com",
            password="Password123!",
            first_name="Fatma",
            last_name="Trabelsi",
        )
        self.participant2 = User.objects.create_user(
            username="participant_2",
            email="p2@example.com",
            password="Password123!",
            first_name="Ahmed",
            last_name="Gharbi",
        )
        self.admin_user = User.objects.create_superuser(
            username="admin_verslevert",
            email="admin@example.com",
            password="Password123!",
            first_name="Admin",
            last_name="Eco",
        )

    # --------------------------------------------------------------------------
    # E-01 : En tant qu'utilisateur, je veux proposer un événement
    # CA : Date dans le futur. Statut « en attente ».
    # --------------------------------------------------------------------------
    def test_e01_citizen_proposes_event_future_date_pending_status(self):
        self.client.force_login(self.citizen)
        future_date = (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Nettoyage des berges du lac",
            "objective": "Ramasser 50 kg de plastiques avec les riverains.",
            "location": "Berges du Lac, Tunis",
            "date": future_date,
            "capacity": 20,
        }
        response = self.client.post(reverse("events:create"), data)
        self.assertEqual(response.status_code, 302)

        event = Event.objects.get(title="Nettoyage des berges du lac")
        self.assertEqual(event.organizer, self.citizen)
        self.assertEqual(event.status, Event.Status.PENDING)
        self.assertEqual(event.capacity, 20)
        self.assertTrue(event.is_upcoming)

    def test_e01_cannot_propose_event_with_past_date(self):
        past_date = timezone.now() - timedelta(days=2)
        form = EventProposalForm(
            data={
                "title": "Événement hier",
                "objective": "Objectif rétroactif",
                "location": "Tunis",
                "date": past_date.strftime("%Y-%m-%dT%H:%M"),
                "capacity": 10,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)
        self.assertIn("futur", form.errors["date"][0].lower())

    # --------------------------------------------------------------------------
    # E-02 : En tant qu'admin, je veux valider ou refuser un événement, ou en créer un directement
    # CA : Événement admin publié immédiatement.
    # --------------------------------------------------------------------------
    def test_e02_admin_creates_event_published_immediately(self):
        self.client.force_login(self.admin_user)
        future_date = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Grand Défi Reboisement",
            "objective": "Planter 100 arbustes indigènes.",
            "location": "Parc du Belvédère",
            "date": future_date,
            "capacity": 50,
        }
        response = self.client.post(reverse("events:create"), data)
        self.assertEqual(response.status_code, 302)

        event = Event.objects.get(title="Grand Défi Reboisement")
        self.assertEqual(event.status, Event.Status.PUBLISHED)
        self.assertEqual(event.organizer, self.admin_user)

    def test_e02_admin_validates_or_refuses_event(self):
        event = Event.objects.create(
            title="Atelier compostage",
            objective="Apprendre à fabriquer son compost.",
            location="Ariana",
            date=timezone.now() + timedelta(days=3),
            organizer=self.citizen,
            status=Event.Status.PENDING,
        )

        # Non-admin cannot validate (PermissionDenied / 403)
        self.client.force_login(self.participant1)
        resp_forbidden = self.client.post(reverse("events:admin_validate", kwargs={"pk": event.pk}))
        self.assertEqual(resp_forbidden.status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PENDING)

        # Admin validates -> PUBLISHED
        self.client.force_login(self.admin_user)
        resp_validate = self.client.post(reverse("events:admin_validate", kwargs={"pk": event.pk}))
        self.assertEqual(resp_validate.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

        # Admin refuses -> REFUSED
        resp_refuse = self.client.post(reverse("events:admin_refuse", kwargs={"pk": event.pk}))
        self.assertEqual(resp_refuse.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.REFUSED)

    # --------------------------------------------------------------------------
    # E-03 : En tant qu'utilisateur, je veux m'inscrire et me désinscrire d'un événement à venir
    # CA : Refusé si complet ou passé. Un seul enregistrement par utilisateur.
    # --------------------------------------------------------------------------
    def test_e03_register_and_unregister_successfully(self):
        event = Event.objects.create(
            title="Clean Walk Sidi Bou Saïd",
            objective="Ramassage citoyen.",
            location="Sidi Bou Saïd",
            date=timezone.now() + timedelta(days=4),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
            capacity=10,
        )

        self.client.force_login(self.participant1)
        # S'inscrire
        resp = self.client.post(reverse("events:register", kwargs={"pk": event.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(EventRegistration.objects.filter(event=event, user=self.participant1).exists())
        self.assertEqual(event.registrations_count, 1)

        # Se désinscrire
        resp_unreg = self.client.post(reverse("events:unregister", kwargs={"pk": event.pk}))
        self.assertEqual(resp_unreg.status_code, 302)
        self.assertFalse(EventRegistration.objects.filter(event=event, user=self.participant1).exists())
        self.assertEqual(event.registrations_count, 0)

    def test_e03_single_registration_per_user_refuses_duplicate(self):
        event = Event.objects.create(
            title="Plage Propre",
            objective="Nettoyage.",
            location="La Marsa",
            date=timezone.now() + timedelta(days=2),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )
        event.register(self.participant1)

        # Deuxième inscription refusée (ValidationError)
        with self.assertRaises(ValidationError):
            event.register(self.participant1)

    def test_e03_registration_refused_if_event_full(self):
        event = Event.objects.create(
            title="Atelier Réparation Vélo",
            objective="Réparer son vélo ensemble.",
            location="Menzah 1",
            date=timezone.now() + timedelta(days=2),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
            capacity=1,
        )
        event.register(self.participant1)
        self.assertTrue(event.is_full)

        with self.assertRaises(ValidationError):
            event.register(self.participant2)

    def test_e03_registration_refused_if_event_past(self):
        past_event = Event.objects.create(
            title="Événement Hier",
            objective="Déjà terminé.",
            location="Centre-ville",
            date=timezone.now() - timedelta(hours=2),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )
        with self.assertRaises(ValidationError):
            past_event.register(self.participant1)

    def test_e03_registration_refused_if_not_published(self):
        pending_event = Event.objects.create(
            title="En attente",
            objective="Pas encore validé.",
            location="Centre-ville",
            date=timezone.now() + timedelta(days=5),
            organizer=self.citizen,
            status=Event.Status.PENDING,
        )
        with self.assertRaises(ValidationError):
            pending_event.register(self.participant1)

    # --------------------------------------------------------------------------
    # E-04 : En tant qu'organisateur, je veux confirmer la présence des inscrits après l'événement
    # CA : Possible seulement après la date. Liste cochable.
    # --------------------------------------------------------------------------
    def test_e04_attendance_forbidden_before_event_date(self):
        future_event = Event.objects.create(
            title="Futur événement",
            objective="Nettoyage.",
            location="Carthage",
            date=timezone.now() + timedelta(days=2),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )
        future_event.register(self.participant1)

        self.client.force_login(self.citizen)
        resp = self.client.get(reverse("events:attendance", kwargs={"pk": future_event.pk}))
        # Redirigé avec message d'erreur car pas encore passé
        self.assertEqual(resp.status_code, 302)

        with self.assertRaises(ValidationError):
            future_event.confirm_attendance([self.participant1.pk], by_user=self.citizen)

    def test_e04_attendance_confirmation_after_date_with_checkbox_list(self):
        past_event = Event.objects.create(
            title="Événement passé",
            objective="Terminé.",
            location="La Goulette",
            date=timezone.now() - timedelta(hours=3),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )
        reg1 = EventRegistration.objects.create(event=past_event, user=self.participant1)
        reg2 = EventRegistration.objects.create(event=past_event, user=self.participant2)

        self.client.force_login(self.citizen)
        # GET affiche la liste cochable
        get_resp = self.client.get(reverse("events:attendance", kwargs={"pk": past_event.pk}))
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "Fatma")
        self.assertContains(get_resp, "Ahmed")

        # POST coche participant1 présent, participant2 absent
        post_resp = self.client.post(
            reverse("events:attendance", kwargs={"pk": past_event.pk}),
            {"present_user_ids": [str(self.participant1.pk)]},
        )
        self.assertEqual(post_resp.status_code, 302)

        reg1.refresh_from_db()
        reg2.refresh_from_db()
        self.assertTrue(reg1.present)
        self.assertFalse(reg2.present)
        self.assertEqual(past_event.confirmed_attendees_count, 1)

    # --------------------------------------------------------------------------
    # E-05 : En tant que participant confirmé, je veux recevoir mes points
    # CA : Points attribués une seule fois, à la clôture, via M2.
    # --------------------------------------------------------------------------
    @patch("gamification.services.award_points", autospec=True)
    def test_e05_points_awarded_once_at_closing_via_m2(self, award_points):
        past_event = Event.objects.create(
            title="Collecte de mégots",
            objective="Ramasser les mégots.",
            location="Centre urbain",
            date=timezone.now() - timedelta(hours=4),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
            points_reward=50,
        )
        reg1 = EventRegistration.objects.create(event=past_event, user=self.participant1, present=True)
        reg2 = EventRegistration.objects.create(event=past_event, user=self.participant2, present=False)

        # Clôture de l'événement
        past_event.close_and_award_points(
            collected_quantity="15 000 mégots",
            result_summary="Grosse participation collective.",
            by_user=self.citizen,
        )

        reg1.refresh_from_db()
        reg2.refresh_from_db()
        self.assertTrue(reg1.points_awarded)
        self.assertEqual(reg1.points_amount, 50)
        self.assertFalse(reg2.points_awarded)
        self.assertEqual(reg2.points_amount, 0)
        self.assertEqual(past_event.status, Event.Status.CLOSED)
        award_points.assert_called_once()
        self.assertEqual(award_points.call_args.kwargs["source_type"], "event")
        self.assertEqual(award_points.call_args.kwargs["source_id"], past_event.pk)
        self.assertEqual(award_points.call_args.kwargs["base_points"], 50)

        # Vérification qu'une seconde clôture n'attribue pas les points deux fois (une seule fois)
        result_second_award = reg1.award_points(50)
        self.assertFalse(result_second_award)
        self.assertEqual(reg1.points_amount, 50)
        self.assertEqual(award_points.call_count, 1)

    # --------------------------------------------------------------------------
    # E-06 : En tant qu'organisateur, je veux publier le résultat (quantité, nombre)
    # CA : Visible sur la page de l'événement clôturé.
    # --------------------------------------------------------------------------
    def test_e06_publish_result_visible_on_closed_event_page(self):
        past_event = Event.objects.create(
            title="Dépollution Oued",
            objective="Nettoyer l'oued.",
            location="Manouba",
            date=timezone.now() - timedelta(days=1),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )
        EventRegistration.objects.create(event=past_event, user=self.participant1, present=True)

        self.client.force_login(self.citizen)
        close_resp = self.client.post(
            reverse("events:close", kwargs={"pk": past_event.pk}),
            {
                "collected_quantity": "85 kg de plastique",
                "actual_participants_count": 12,
                "result_summary": "Objectif dépassé avec succès grâce aux bénévoles !",
            },
        )
        self.assertEqual(close_resp.status_code, 302)

        past_event.refresh_from_db()
        self.assertEqual(past_event.status, Event.Status.CLOSED)
        self.assertEqual(past_event.collected_quantity, "85 kg de plastique")
        self.assertEqual(past_event.actual_participants_count, 12)

        # Visible sur la page de détail de l'événement
        detail_resp = self.client.get(reverse("events:detail", kwargs={"pk": past_event.pk}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "85 kg de plastique")
        self.assertContains(detail_resp, "12 participant")
        self.assertContains(detail_resp, "Objectif dépassé avec succès")
        self.assertContains(detail_resp, "Clôturé")

        # Visible également dans l'onglet des résultats
        results_resp = self.client.get(reverse("events:results"))
        self.assertEqual(results_resp.status_code, 200)
        self.assertContains(results_resp, "85 kg de plastique")
        self.assertContains(results_resp, "Dépollution Oued")

    # --------------------------------------------------------------------------
    # Navigation et Vues du module Événements
    # --------------------------------------------------------------------------
    def test_navigation_and_tab_views(self):
        self.client.force_login(self.citizen)

        # Redirection index -> upcoming
        resp_index = self.client.get(reverse("events:index"))
        self.assertRedirects(resp_index, reverse("events:upcoming"))

        # Onglet À venir
        resp_upcoming = self.client.get(reverse("events:upcoming"))
        self.assertEqual(resp_upcoming.status_code, 200)

        # Onglet Mes événements
        resp_mine = self.client.get(reverse("events:mine"))
        self.assertEqual(resp_mine.status_code, 200)

        # Onglet Résultats
        resp_results = self.client.get(reverse("events:results"))
        self.assertEqual(resp_results.status_code, 200)

    # --------------------------------------------------------------------------
    # Fonctionnalités Innovantes d'Intelligence Artificielle (Événements)
    # --------------------------------------------------------------------------
    def test_ai_copilot_endpoint(self):
        self.client.force_login(self.citizen)
        resp = self.client.post(
            reverse("events:ai_copilot"),
            {"topic": "Nettoyage forêt de Rades", "location": "Rades"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("title", data)
        self.assertIn("objective", data)
        self.assertIn("checklist", data)
        self.assertIn("suggested_capacity", data)
        self.assertTrue(len(data["checklist"]) > 0)

    def test_ai_environmental_impact_analysis(self):
        self.client.force_login(self.citizen)
        event = Event.objects.create(
            title="Clean Up Plage",
            objective="Ramasser les déchets plastiques.",
            location="Gammarth",
            date=timezone.now() - timedelta(days=2),
            organizer=self.citizen,
            status=Event.Status.CLOSED,
            collected_quantity="60 kg de plastique",
            actual_participants_count=15,
        )

        resp = self.client.get(reverse("events:ai_impact", kwargs={"pk": event.pk}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("estimated_co2_kg", data)
        self.assertIn("equivalences", data)
        self.assertTrue(float(data["estimated_co2_kg"]) > 0)

        # Vérification persistance sur le modèle Event
        event.refresh_from_db()
        self.assertIsNotNone(event.co2_avoided)
        self.assertIsNotNone(event.impact_analysis_dict)

    def test_ai_social_media_kit(self):
        self.client.force_login(self.citizen)
        event = Event.objects.create(
            title="Plantation 50 arbres",
            objective="Reboisement urbain.",
            location="Parc Urbain",
            date=timezone.now() - timedelta(days=1),
            organizer=self.citizen,
            status=Event.Status.CLOSED,
            collected_quantity="50 arbres plantés",
            actual_participants_count=20,
        )

        resp = self.client.get(reverse("events:ai_social_kit", kwargs={"pk": event.pk}))
        self.assertEqual(resp.status_code, 200)
        kit = resp.json()
        self.assertIn("instagram_post", kit)
        self.assertIn("x_post", kit)
        self.assertIn("press_snippet", kit)
        self.assertIn("Plantation", kit["instagram_post"])

    def test_ai_moderation_admin(self):
        event = Event.objects.create(
            title="Événement à valider",
            objective="Nettoyage et sensibilisation au tri sélectif.",
            location="Ariana",
            date=timezone.now() + timedelta(days=4),
            organizer=self.citizen,
            status=Event.Status.PENDING,
        )

        # Un citoyen normal n'a pas accès à la modération IA (403)
        self.client.force_login(self.citizen)
        resp_forbidden = self.client.get(reverse("events:ai_moderate", kwargs={"pk": event.pk}))
        self.assertEqual(resp_forbidden.status_code, 403)

        # L'administrateur y a accès
        self.client.force_login(self.admin_user)
        resp_admin = self.client.get(reverse("events:ai_moderate", kwargs={"pk": event.pk}))
        self.assertEqual(resp_admin.status_code, 200)
        mod_data = resp_admin.json()
        self.assertIn("is_eco_relevant", mod_data)
        self.assertIn("recommendation", mod_data)
        self.assertIn("score", mod_data)

    def test_ai_smart_search_recommendations(self):
        # Création d'événements à venir
        Event.objects.create(
            title="Opération Plage Propre",
            objective="Ramassage sur le sable et sensibilisation marine.",
            location="La Marsa Plage",
            date=timezone.now() + timedelta(days=2),
            organizer=self.citizen,
            status=Event.Status.PUBLISHED,
        )

        resp = self.client.post(
            reverse("events:ai_search"),
            {"query": "Je cherche une action sur la plage pour nettoyer le sable"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("summary", data)
        self.assertIn("recommendations", data)
        self.assertTrue(len(data["recommendations"]) > 0)


class EventWeatherTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="weather_user",
            email="weather@example.com",
            password="weather-test-password",
        )
        self.event = Event.objects.create(
            title="Nettoyage de la plage",
            objective="Collecter les déchets sur la plage.",
            location="La Marsa, Tunisia",
            date=timezone.now() + timedelta(days=3),
            organizer=self.user,
            status=Event.Status.PUBLISHED,
        )

    def _provider_response(self, payload):
        request = httpx.Request("GET", "https://api.open-meteo.com/")
        return httpx.Response(200, json=payload, request=request)

    @patch("events.weather.httpx.get")
    def test_weather_endpoint_returns_forecast_for_event_time(self, mock_get):
        event_local_time = self.event.date.astimezone(ZoneInfo("Africa/Tunis"))
        forecast_time = event_local_time.replace(minute=0,second=0,microsecond=0,)

        if event_local_time.minute >= 30:
             forecast_time += timedelta(hours=1)        
             mock_get.side_effect = [
            self._provider_response(
                {
                    "results": [
                        {
                            "name": "La Marsa",
                            "country": "Tunisia",
                            "latitude": 36.878,
                            "longitude": 10.324,
                        }
                    ]
                }
            ),
            self._provider_response(
                {
                    "timezone": "Africa/Tunis",
                    "hourly": {
                        "time": [forecast_time.strftime("%Y-%m-%dT%H:%M")],
                        "temperature_2m": [24.5],
                        "apparent_temperature": [25.1],
                        "precipitation_probability": [10],
                        "weather_code": [1],
                        "wind_speed_10m": [12.0],
                    },
                }
            ),
        ]

        response = self.client.get(reverse("events:weather", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "Majoritairement dégagé")
        self.assertEqual(response.json()["temperature_c"], 24.5)
        self.assertEqual(response.json()["precipitation_probability"], 10)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args.kwargs["params"]["forecast_days"], 16)

    @patch("events.weather.httpx.get")
    def test_past_event_weather_is_not_requested(self, mock_get):
        self.event.date = timezone.now() - timedelta(hours=1)
        self.event.save(update_fields=["date"])

        response = self.client.get(reverse("events:weather", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        mock_get.assert_not_called()

    @patch("events.weather.httpx.get")
    def test_unpublished_event_has_no_weather_endpoint(self, mock_get):
        self.event.status = Event.Status.PENDING
        self.event.save(update_fields=["status"])

        response = self.client.get(reverse("events:weather", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 404)
        mock_get.assert_not_called()

    @patch("events.weather.httpx.get")
    def test_weather_provider_failure_is_reported(self, mock_get):
        request = httpx.Request("GET", "https://geocoding-api.open-meteo.com/")
        mock_get.side_effect = httpx.ConnectError("offline", request=request)

        response = self.client.get(reverse("events:weather", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["available"])
        self.assertIn("indisponible", response.json()["message"])

    def test_upcoming_published_event_detail_shows_weather_panel(self):
        response = self.client.get(reverse("events:detail", kwargs={"pk": self.event.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Météo à l'heure de l'événement")
        self.assertContains(response, "Open-Meteo")
