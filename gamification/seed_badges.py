# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django
django.setup()

from gamification.models import Badge

BADGES = [
    dict(code="FIRST_STEP",    name="Premier pas",         icon="\U0001f331", tier="BRONZE", criteria_type="TOTAL_POINTS",  threshold=1,   description="Gagnez vos premiers points."),
    dict(code="GREEN_50",      name="Geste vert",          icon="\U0001f343", tier="BRONZE", criteria_type="TOTAL_POINTS",  threshold=50,  description="Atteignez 50 points."),
    dict(code="EXPLORER_200",  name="Explorateur",         icon="\U0001f33f", tier="SILVER", criteria_type="TOTAL_POINTS",  threshold=200, description="Atteignez 200 points."),
    dict(code="CHAMPION_500",  name="Champion vert",       icon="\U0001f3c6", tier="GOLD",   criteria_type="TOTAL_POINTS",  threshold=500, description="Atteignez 500 points !"),
    dict(code="PROOF_1",       name="Ma premiere preuve",  icon="\U0001f4c4", tier="BRONZE", criteria_type="ACTION_COUNT",  threshold=1,   description="Soumettez votre premiere preuve."),
    dict(code="PROOF_5",       name="5 preuves",           icon="\U0001f4cb", tier="SILVER", criteria_type="ACTION_COUNT",  threshold=5,   description="Soumettez 5 preuves validees."),
    dict(code="TRANSPORT_PRO", name="Voyageur durable",    icon="\U0001f68c", tier="SILVER", criteria_type="ACTION_COUNT",  threshold=3,   criteria_action_type="TRANSPORT_TICKET", description="3 tickets de transport valides."),
]

created = 0
for b in BADGES:
    obj, flag = Badge.objects.get_or_create(code=b["code"], defaults=b)
    if flag:
        created += 1
        print("Created:", b["code"])
    else:
        print("Exists: ", b["code"])
print("Done:", created, "badges created")
