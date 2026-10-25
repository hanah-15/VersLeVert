from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from gamification.management.commands.seed_proof_types import PROOF_TYPES
from gamification.models import EcoProof, ImpactFactor, ProofType
from gamification.ocr.parsers import check_keyword_requirements, match_keyword_groups
from gamification.services.rules import effective_proof_cap, effective_window_days


class SeedProofTypesTests(TestCase):
    def test_running_seed_twice_is_idempotent(self):
        call_command("seed_proof_types", verbosity=0)
        first = list(
            ProofType.objects.order_by("code").values(
                "code",
                "category",
                "label_fr",
                "description_fr",
                "tips_fr",
                "keyword_groups",
                "cap_count",
                "window_days",
                "is_active",
            )
        )

        call_command("seed_proof_types", verbosity=0)

        second = list(
            ProofType.objects.order_by("code").values(
                "code",
                "category",
                "label_fr",
                "description_fr",
                "tips_fr",
                "keyword_groups",
                "cap_count",
                "window_days",
                "is_active",
            )
        )
        self.assertEqual(first, second)

    def test_seed_twice_preserves_existing_admin_edits(self):
        call_command("seed_proof_types", verbosity=0)
        proof_type = ProofType.objects.get(code="ENERGY_RENOVATION")
        factor = ImpactFactor.objects.get(action_type=proof_type.action_type)
        proof_type.cap_count = 7
        proof_type.keyword_groups = [{"terms": ["admin keyword"], "required": True}]
        proof_type.description_fr = "Description personnalisée."
        proof_type.save()
        factor.points_per_unit = 999
        factor.save(update_fields=["points_per_unit"])

        call_command("seed_proof_types", verbosity=0)

        proof_type.refresh_from_db()
        factor.refresh_from_db()
        self.assertEqual(proof_type.cap_count, 7)
        self.assertEqual(proof_type.keyword_groups, [{"terms": ["admin keyword"], "required": True}])
        self.assertEqual(proof_type.description_fr, "Description personnalisée.")
        self.assertEqual(factor.points_per_unit, 999)

    def test_reset_restores_builtin_defaults(self):
        call_command("seed_proof_types", verbosity=0)
        proof_type = ProofType.objects.get(code="ENERGY_RENOVATION")
        factor = ImpactFactor.objects.get(action_type=proof_type.action_type)
        proof_type.cap_count = 7
        proof_type.keyword_groups = [{"terms": ["admin keyword"], "required": True}]
        proof_type.description_fr = "Description personnalisée."
        proof_type.save()
        factor.points_per_unit = 999
        factor.save(update_fields=["points_per_unit"])

        call_command("seed_proof_types", "--reset", verbosity=0)

        proof_type.refresh_from_db()
        factor.refresh_from_db()
        self.assertEqual(proof_type.cap_count, 2)
        self.assertEqual(proof_type.window_days, 90)
        self.assertEqual(
            proof_type.description_fr,
            "Justifiez une rénovation énergétique, une installation solaire ou l'achat d'un appareil économe.",
        )
        self.assertEqual(factor.points_per_unit, 150)
        self.assertNotIn(
            "devis",
            str(proof_type.keyword_groups).casefold(),
        )

    def test_seed_retires_merged_sources_and_exposes_fourteen_active_types(self):
        call_command("seed_proof_types", verbosity=0)
        expected_active_codes = {item["code"] for item in PROOF_TYPES}
        self.assertEqual(
            set(ProofType.objects.filter(is_active=True).values_list("code", flat=True)),
            expected_active_codes,
        )
        self.assertEqual(len(expected_active_codes), 14)
        self.assertEqual(
            ProofType.objects.filter(code__in=[
                "LED_BULBS",
                "INSULATION",
                "BIKE_REPAIR",
                "SECONDHAND_ITEM",
                "HOME_COMPOST_PHOTO",
            ], is_active=True).count(),
            0,
        )

    def test_merged_types_use_combined_keywords_points_and_source_caps(self):
        call_command("seed_proof_types", verbosity=0)
        expected = {
            "SMALL_EFFICIENT_EQUIPMENT": (10, 2, "YEAR", {"led", "économiseur"}),
            "ENERGY_RENOVATION": (150, 2, "YEAR", {"isolation", "photovoltaique", "inverter"}),
            "SECONDHAND_OR_REFURBISHED": (
                15, 6, "MONTH", {"friperie", "meuble", "reconditionné"},
            ),
            "REPAIR_RECEIPT": (15, 4, "MONTH", {"bicyclette", "cordonnier"}),
            "RESPONSIBLE_SHOPPING": (10, 6, "MONTH", {"vrac", "producteur", "fermier"}),
            "ECO_ACTION_PHOTO": (25, 1, "QUARTER", set()),
        }
        for code, (points, cap_count, cap_period, required_terms) in expected.items():
            proof_type = ProofType.objects.get(code=code)
            terms = {
                term
                for group in proof_type.keyword_groups
                for term in group["terms"]
            }
            self.assertEqual(proof_type.points_awarded(), points)
            self.assertEqual((proof_type.cap_count, proof_type.cap_period), (cap_count, cap_period))
            self.assertTrue(required_terms.issubset(terms))

        energy_terms = {
            term
            for group in ProofType.objects.get(code="ENERGY_RENOVATION").keyword_groups
            for term in group["terms"]
        }
        self.assertFalse(any("devis" in term.casefold() for term in energy_terms))
        energy_type = ProofType.objects.get(code="ENERGY_RENOVATION")
        self.assertTrue(energy_type.keyword_groups[0]["required"])
        self.assertEqual(energy_type.min_groups, 2)
        _, quote_matches = match_keyword_groups(
            "Devis solaire travaux",
            energy_type.keyword_groups,
        )
        self.assertFalse(
            check_keyword_requirements(
                energy_type.keyword_groups,
                quote_matches,
                energy_type.min_groups,
            )
        )

    def test_retired_seed_choices_are_not_shown_on_upload_page(self):
        call_command("seed_proof_types", verbosity=0)
        user = User.objects.create_user(
            username="seed-page-user",
            email="seed-page@example.com",
            password="SeedPagePass123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("proofs:new"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Bon de dépôt en centre de tri")
        self.assertNotContains(response, "Reçu de don alimentaire")
        self.assertContains(response, "Ticket bus, métro, tram ou train")
        self.assertContains(response, "Petit équipement économe")
        self.assertContains(response, "reconditionné")
        self.assertNotIn(
            ProofType.Category.WASTE,
            {category for category, _label in response.context["proof_categories"]},
        )

    def test_seed_uses_per_type_windows_and_textile_photo_has_no_date(self):
        call_command("seed_proof_types", verbosity=0)

        active_types = ProofType.objects.filter(is_active=True)
        self.assertEqual(active_types.count(), len(PROOF_TYPES))
        self.assertEqual(
            active_types.exclude(description_fr="").count(),
            active_types.count(),
        )
        self.assertEqual(
            active_types.exclude(tips_fr="").count(),
            active_types.count(),
        )
        descriptions = list(active_types.values_list("description_fr", flat=True))
        tips = list(active_types.values_list("tips_fr", flat=True))
        self.assertEqual(len(descriptions), len(set(descriptions)))
        self.assertEqual(len(tips), len(set(tips)))
        self.assertEqual(ProofType.objects.get(code="TRANSPORT_TICKET").window_days, 30)
        self.assertEqual(ProofType.objects.get(code="TRANSPORT_PASS").window_days, 45)
        self.assertEqual(ProofType.objects.get(code="ENERGY_RENOVATION").window_days, 90)
        textile_label = ProofType.objects.get(code="TEXTILE_LABEL")
        self.assertTrue(textile_label.photo_only)
        self.assertFalse(textile_label.requires_date)
        self.assertEqual(textile_label.min_groups, 1)
        self.assertIsNone(textile_label.window_days)
        photo_type = ProofType.objects.get(code="ECO_ACTION_PHOTO")
        self.assertTrue(photo_type.photo_only)
        self.assertFalse(photo_type.requires_date)
        self.assertNotEqual(
            ProofType.objects.get(code="TEXTILE_LABEL").tips_fr,
            photo_type.tips_fr,
        )

    def test_legacy_proofs_keep_retired_type_and_remain_visible(self):
        old_type = ProofType.objects.create(
            code="BIKE_REPAIR",
            category=ProofType.Category.MOBILITY,
            label_fr="Ancienne réparation de vélo",
            action_type="PROOF_BIKE_REPAIR",
            cap_count=2,
            cap_period=ProofType.CapPeriod.MONTH,
        )
        factor = ImpactFactor.objects.create(
            action_type="PROOF_BIKE_REPAIR",
            label="Ancienne réparation de vélo",
            unit=ImpactFactor.Unit.PROOF,
            points_per_unit=10,
        )
        user = User.objects.create_user(
            username="legacy-proof-user",
            email="legacy-proof@example.com",
            password="safe-test-password",
        )
        proof = EcoProof.objects.create(
            user=user,
            proof_type=old_type,
            status=EcoProof.Status.REJECTED,
        )

        call_command("seed_proof_types", verbosity=0)

        old_type.refresh_from_db()
        factor.refresh_from_db()
        proof.refresh_from_db()
        self.assertFalse(old_type.is_active)
        self.assertFalse(factor.is_active)
        self.assertEqual(proof.proof_type_id, old_type.pk)
        self.client.force_login(user)
        response = self.client.get(reverse("proofs:detail", kwargs={"pk": proof.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ancienne réparation de vélo")

    def test_upload_page_shows_real_caps_not_development_multiplier(self):
        call_command("seed_proof_types", verbosity=0)
        user = User.objects.create_user(
            username="cap-page-user",
            email="cap-page@example.com",
            password="safe-test-password",
        )
        self.client.force_login(user)

        with override_settings(PROOF_CAP_MULTIPLIER=10):
            response = self.client.get(reverse("proofs:new"))

        self.assertContains(response, "Jusqu'à 2 preuves par an")
        self.assertContains(response, "Jusqu'à 1 preuve par trimestre")
        self.assertNotContains(response, "Jusqu'à 20 preuves par an")

    def test_proof_cards_are_sorted_by_points_within_categories(self):
        call_command("seed_proof_types", verbosity=0)
        user = User.objects.create_user(
            username="sorted-page-user",
            email="sorted-page@example.com",
            password="safe-test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("proofs:new"))

        energy_cards = [
            proof_type
            for proof_type in response.context["proof_types"]
            if proof_type.category == ProofType.Category.ENERGY
        ]
        self.assertEqual(
            [proof_type.points_value for proof_type in energy_cards],
            sorted(proof_type.points_value for proof_type in energy_cards),
        )
        self.assertContains(response, "<dialog", html=False)
        self.assertContains(response, "Étape 2 sur 3")
        self.assertContains(response, "Étape 3 sur 3")
        self.assertContains(response, "Envoyer pour analyse")
        self.assertNotContains(response, "vérification manuelle")
        self.assertContains(response, 'id="proof-selected-tip"')
        self.assertContains(response, 'id="proof-drop-zone" class="proof-dropzone"')
        self.assertNotContains(response, "cursor-not-allowed opacity-60")

    @override_settings(PROOF_WINDOW_OVERRIDE_DAYS=365, PROOF_CAP_MULTIPLIER=10)
    def test_development_overrides_affect_runtime_rules_not_seeded_defaults(self):
        call_command("seed_proof_types", verbosity=0)
        proof_type = ProofType.objects.get(code="TRANSPORT_TICKET")

        self.assertEqual(proof_type.window_days, 30)
        self.assertEqual(effective_window_days(proof_type), 365)
        self.assertEqual(effective_proof_cap(proof_type.cap_count), 200)
