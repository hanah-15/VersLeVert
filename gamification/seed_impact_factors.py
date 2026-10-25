"""
Seed initial ImpactFactor entries for the gamification module.

Run with:
    python manage.py shell < gamification/seed_impact_factors.py
    OR
    python manage.py runscript seed_impact_factors   (if django-extensions installed)

These are starting values — the admin can adjust them at /admin/ or via the dashboard.
Sources: ADEME approximations.
"""

import django
django.setup()

from gamification.models import ImpactFactor

FACTORS = [
    # Eco Proofs
    dict(action_type="ELECTRICITY_BILL",  label="Facture d'électricité verte",    unit="proof", points_per_unit=50,  co2_kg_per_unit="0.0000"),
    dict(action_type="TRANSPORT_TICKET",  label="Ticket de transport en commun",  unit="proof", points_per_unit=30,  co2_kg_per_unit="0.0000"),
    dict(action_type="TEXTILE_LABEL",     label="Étiquette textile éthique",       unit="proof", points_per_unit=40,  co2_kg_per_unit="0.0000"),
    dict(action_type="OTHER",             label="Autre preuve écologique",          unit="proof", points_per_unit=20,  co2_kg_per_unit="0.0000"),
    # Waste collection (used by M3 — Hana)
    dict(action_type="WASTE_ORGANIC",     label="Déchets organiques collectés",    unit="kg",    points_per_unit=10,  co2_kg_per_unit="0.4500"),
    dict(action_type="WASTE_PLASTIC",     label="Déchets plastiques collectés",    unit="kg",    points_per_unit=15,  co2_kg_per_unit="1.8000"),
    # Events (used by M4 — Oussema)
    dict(action_type="EVENT_PARTICIPANT", label="Participation à un événement",    unit="count", points_per_unit=25,  co2_kg_per_unit="0.0000"),
    dict(action_type="EVENT_ORGANIZER",   label="Organisation d'un événement",     unit="count", points_per_unit=100, co2_kg_per_unit="0.0000"),
    # Challenges (used by M2 — Aymen)
    dict(action_type="CHALLENGE_BONUS",   label="Bonus de défi officiel complété", unit="count", points_per_unit=1,   co2_kg_per_unit="0.0000"),
]

created = 0
skipped = 0
for f in FACTORS:
    obj, created_flag = ImpactFactor.objects.get_or_create(
        action_type=f["action_type"],
        defaults=f,
    )
    if created_flag:
        created += 1
        print(f"  ✅ Created: {obj}")
    else:
        skipped += 1
        print(f"  ⏭  Already exists: {obj}")

print(f"\nDone — {created} created, {skipped} already existed.")
