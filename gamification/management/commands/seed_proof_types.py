from django.core.management.base import BaseCommand
from django.db import transaction

from gamification.models import ImpactFactor, ProofType


PROOF_TYPES = [
    ("TRANSPORT_TICKET", "MOBILITY", "Ticket bus, métro, tram ou train", 5, 20, "MONTH", 30, [["transtu", "sncft", "metro", "bus", "tram"], ["ticket", "billet", "transport"]]),
    ("TRANSPORT_PASS", "MOBILITY", "Abonnement transport en commun", 40, 1, "MONTH", 45, [["abonnement", "carte", "اشتراك"], ["transtu", "sncft", "metro", "bus", "tram", "mensuel"]]),
    ("BIKE_REPAIR", "MOBILITY", "Réparation de vélo", 10, 2, "MONTH", 30, [["vélo", "velo", "bicyclette", "trottinette", "vtt"], ["facture", "ticket", "réparation", "reparation"]]),
    ("EV_CHARGE", "MOBILITY", "Reçu de recharge véhicule électrique", 10, 8, "MONTH", 30, [["recharge", "borne", "kwh", "électrique", "electrique"], ["facture", "ticket", "reçu", "recu"]]),
    ("BIKE_PURCHASE", "MOBILITY", "Facture vélo, vélo électrique ou trottinette", 150, 1, "YEAR", 60, [["vélo", "velo", "bicyclette", "trottinette"], ["facture", "achat"]]),
    ("EV_PURCHASE", "MOBILITY", "Facture véhicule électrique ou hybride", 300, 1, "TWO_YEARS", 90, [["véhicule", "vehicule", "électrique", "electrique", "hybride"], ["facture", "achat"]]),
    ("ELECTRICITY_BILL", "ENERGY", "Facture d'électricité", 15, 1, "MONTH", 60, [["steg", "électricité", "electricite", "kwh", "كهرباء"], ["facture", "consommation", "période", "periode", "فاتورة"]]),
    ("GAS_BILL", "ENERGY", "Facture de gaz", 15, 1, "MONTH", 60, [["steg", "gaz", "غاز"], ["facture", "consommation", "m3", "فاتورة"]]),
    ("LED_BULBS", "ENERGY", "Facture d'ampoules LED", 10, 2, "YEAR", 60, [["led", "ampoule", "lampe"], ["facture", "ticket", "quantité", "quantite"]]),
    ("EFFICIENT_APPLIANCE", "ENERGY", "Facture d'appareil économe (classe A ou B)", 60, 2, "YEAR", 60, [["classe", "énergie", "energie", "a+", "inverter"], ["facture", "garantie", "référence", "reference"]]),
    ("INSULATION", "ENERGY", "Facture d'isolation ou double vitrage", 200, 1, "YEAR", 90, [["isolation", "double vitrage", "isolant", "thermique"], ["facture", "devis", "travaux"]]),
    ("SOLAR_EQUIPMENT", "ENERGY", "Facture de panneau solaire ou chauffe-eau solaire", 300, 1, "YEAR", 90, [["solaire", "photovoltaïque", "photovoltaique", "panneau"], ["facture", "devis", "installation"]]),
    ("WATER_BILL", "WATER", "Facture d'eau", 15, 1, "MONTH", 60, [["sonede", "eau", "m3", "ماء"], ["facture", "consommation", "فاتورة"]]),
    ("WATER_SAVING_DEVICE", "WATER", "Facture d'économiseur d'eau", 15, 2, "YEAR", 60, [["économiseur", "economiseur", "eau", "robinet", "douche"], ["facture", "ticket"]]),
    ("SECONDHAND_CLOTHES", "CONSUMPTION", "Achat de vêtement de seconde main", 10, 6, "MONTH", 30, [["friperie", "occasion", "seconde main", "vintage"], ["ticket", "facture", "total"]]),
    ("SECONDHAND_ITEM", "CONSUMPTION", "Achat d'occasion (meuble, électroménager)", 15, 4, "MONTH", 30, [["occasion", "seconde main", "meuble"], ["facture", "garantie", "ticket"]]),
    ("REFURBISHED_DEVICE", "CONSUMPTION", "Facture d'appareil reconditionné", 40, 2, "YEAR", 60, [["occasion", "reconditionné", "reconditionne", "refurbished"], ["facture", "garantie", "ticket"]]),
    ("REPAIR_RECEIPT", "CONSUMPTION", "Réparation au lieu de remplacer", 15, 4, "MONTH", 30, [["réparation", "reparation", "dépannage", "depannage", "cordonnier"], ["facture", "ticket", "total"]]),
    ("BULK_REFILL", "CONSUMPTION", "Ticket de magasin vrac ou zéro déchet", 10, 6, "MONTH", 30, [["vrac", "recharge", "zéro déchet", "zero dechet", "refill"], ["ticket", "total", "kg"]]),
    ("ORGANIC_LOCAL_MARKET", "CONSUMPTION", "Ticket de marché bio ou producteur local", 10, 4, "MONTH", 30, [["bio", "marché", "marche", "producteur", "local", "fermier"], ["ticket", "total", "kg"]]),
    ("ECO_LABEL_PRODUCT", "CONSUMPTION", "Photo de produit avec écolabel", 5, 10, "MONTH", None, [["ecocert", "fsc", "ecolabel", "fairtrade", "biologique", "bio", "recyclable"]]),
    ("TEXTILE_LABEL", "TEXTILE", "Étiquette vêtement éthique ou recyclé", 10, 4, "MONTH", None, [["coton bio", "organic cotton", "lin", "recyclé", "recycle", "gots", "oeko-tex"]]),
    ("RECYCLING_DEPOSIT", "WASTE", "Bon de dépôt en centre de tri ou point de collecte", 10, 4, "MONTH", 30, [["recyclage", "tri", "collecte", "dépôt", "depot", "déchets", "dechets"], ["bon", "reçu", "recu", "poids", "kg", "date"]]),
    ("FOOD_DONATION", "WASTE", "Reçu de don alimentaire", 15, 2, "MONTH", 30, [["don", "association", "banque alimentaire", "solidarité"], ["reçu", "recu", "attestation", "kg", "date"]]),
    ("WORKSHOP_ATTESTATION", "ENGAGEMENT", "Attestation d'atelier ou de formation écologique", 30, 2, "QUARTER", 90, [["attestation", "certificat", "participation", "atelier", "formation"], ["environnement", "écologie", "ecologie", "climat", "durable"]]),
    ("HOME_COMPOST_PHOTO", "ENGAGEMENT", "Photo d'un composteur domestique", 20, 1, "QUARTER", None, []),
    ("TREE_PLANTING_PHOTO", "ENGAGEMENT", "Photo de plantation d'arbre", 30, 2, "YEAR", None, []),
]


class Command(BaseCommand):
    help = "Seed or update eco-proof types and their points factors."

    @transaction.atomic
    def handle(self, *args, **options):
        for code, category, label, points, cap, period, window, terms in PROOF_TYPES:
            photo_only = code in {"HOME_COMPOST_PHOTO", "TREE_PLANTING_PHOTO"}
            groups = [{"terms": group, "required": False} for group in terms]
            ProofType.objects.update_or_create(
                code=code,
                defaults={
                    "category": category,
                    "label_fr": label,
                    "description_fr": label,
                    "tips_fr": "Photographiez le document entier, net et bien éclairé.",
                    "icon": "camera" if photo_only else "document",
                    "action_type": f"PROOF_{code}",
                    "keyword_groups": groups,
                    "min_groups": 0 if photo_only else 1,
                    "requires_date": not photo_only,
                    "requires_amount": False,
                    "window_days": window,
                    "cap_count": cap,
                    "cap_period": period,
                    "always_review": photo_only or points >= 60,
                    "photo_only": photo_only,
                    "is_active": True,
                },
            )
            ImpactFactor.objects.update_or_create(
                action_type=f"PROOF_{code}",
                defaults={
                    "label": label,
                    "unit": ImpactFactor.Unit.PROOF,
                    "points_per_unit": points,
                    "co2_kg_per_unit": None,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(PROOF_TYPES)} proof types and impact factors."))
