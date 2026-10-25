from django.core.management.base import BaseCommand
from django.db import transaction

from gamification.models import ImpactFactor, ProofType


PROOF_TYPES = [
    {
        "code": "TRANSPORT_TICKET",
        "category": "MOBILITY",
        "label_fr": "Ticket bus, métro, tram ou train",
        "points": 5,
        "cap_count": 20,
        "cap_period": "MONTH",
        "window_days": 30,
        "keyword_groups": [
            ["transtu", "sncft", "metro", "bus", "tram"],
            ["ticket", "billet", "transport"],
        ],
        "description_fr": "Validez un trajet effectué en transport collectif.",
        "tips_fr": "Photographiez le ticket entier ; le réseau, la date, le montant et le transporteur doivent être lisibles.",
    },
    {
        "code": "TRANSPORT_PASS",
        "category": "MOBILITY",
        "label_fr": "Abonnement transport en commun",
        "points": 40,
        "cap_count": 1,
        "cap_period": "MONTH",
        "window_days": 45,
        "keyword_groups": [
            ["abonnement", "carte", "اشتراك"],
            ["transtu", "sncft", "metro", "bus", "tram", "mensuel"],
        ],
        "description_fr": "Justifiez un abonnement actif à un réseau de transport collectif.",
        "tips_fr": "Photographiez la carte ou le reçu d'abonnement avec le réseau, les dates de validité et le montant.",
    },
    {
        "code": "BIKE_PURCHASE",
        "category": "MOBILITY",
        "label_fr": "Facture vélo, vélo électrique ou trottinette",
        "points": 150,
        "cap_count": 1,
        "cap_period": "YEAR",
        "window_days": 60,
        "keyword_groups": [
            ["vélo", "velo", "bicyclette", "trottinette"],
            ["facture", "achat"],
        ],
        "description_fr": "Justifiez l'achat d'un vélo ou d'une trottinette pour vos déplacements.",
        "tips_fr": "Joignez la facture avec la date, le modèle, le montant total et le nom du commerçant.",
    },
    {
        "code": "ELECTRICITY_BILL",
        "category": "ENERGY",
        "label_fr": "Facture d'électricité",
        "points": 15,
        "cap_count": 1,
        "cap_period": "MONTH",
        "window_days": 60,
        "keyword_groups": [
            ["steg", "électricité", "electricite", "kwh", "كهرباء"],
            ["facture", "consommation", "période", "periode", "فاتورة"],
        ],
        "description_fr": "Suivez votre consommation d'électricité avec une facture récente.",
        "tips_fr": "Photographiez la facture STEG entière avec la date, la période, la consommation et le montant total.",
    },
    {
        "code": "GAS_BILL",
        "category": "ENERGY",
        "label_fr": "Facture de gaz",
        "points": 15,
        "cap_count": 1,
        "cap_period": "MONTH",
        "window_days": 60,
        "keyword_groups": [
            ["steg", "gaz", "غاز"],
            ["facture", "consommation", "m3", "فاتورة"],
        ],
        "description_fr": "Justifiez le suivi de votre consommation de gaz.",
        "tips_fr": "Photographiez la facture entière avec la date, la période, la consommation et le montant total.",
    },
    {
        "code": "SMALL_EFFICIENT_EQUIPMENT",
        "category": "ENERGY",
        "label_fr": "Petit équipement économe (LED, économiseur d'eau)",
        "points": 10,
        "cap_count": 2,
        "cap_period": "YEAR",
        "window_days": 60,
        "keyword_groups": [
            [
                "led", "ampoule", "lampe", "économiseur", "economiseur", "eau",
                "robinet", "douche",
            ],
            ["facture", "ticket", "quantité", "quantite"],
        ],
        "description_fr": "Justifiez l'achat d'ampoules LED ou d'un équipement qui réduit la consommation d'eau.",
        "tips_fr": "Le ticket ou la facture doit montrer l'équipement acheté, sa date, le montant total et le commerçant.",
    },
    {
        "code": "ENERGY_RENOVATION",
        "category": "ENERGY",
        "label_fr": "Rénovation ou équipement énergétique (isolation, solaire, appareil classe A ou B)",
        "points": 150,
        "cap_count": 2,
        "cap_period": "YEAR",
        "window_days": 90,
        "keyword_groups": [
            [
                "isolation", "double vitrage", "isolant", "thermique",
                "solaire", "photovoltaïque", "photovoltaique", "panneau",
                "chauffe-eau solaire", "classe", "énergie", "energie", "a+",
                "inverter",
            ],
            ["travaux", "installation", "garantie", "référence", "reference"],
        ],
        "required_keyword_groups": [["facture", "invoice", "فاتورة"]],
        "description_fr": "Justifiez une rénovation énergétique, une installation solaire ou l'achat d'un appareil économe.",
        "tips_fr": "Envoyez une facture (pas un devis) avec la date, les travaux ou le modèle, le montant total et l'entreprise.",
    },
    {
        "code": "WATER_BILL",
        "category": "WATER",
        "label_fr": "Facture d'eau",
        "points": 15,
        "cap_count": 1,
        "cap_period": "MONTH",
        "window_days": 60,
        "keyword_groups": [
            ["sonede", "eau", "m3", "ماء"],
            ["facture", "consommation", "فاتورة"],
        ],
        "description_fr": "Suivez votre consommation d'eau à partir d'une facture SONEDE.",
        "tips_fr": "Photographiez la facture entière avec la date, la période, l'index de consommation et le montant total.",
    },
    {
        "code": "SECONDHAND_OR_REFURBISHED",
        "category": "CONSUMPTION",
        "label_fr": "Achat d'occasion ou reconditionné",
        "points": 15,
        "cap_count": 6,
        "cap_period": "MONTH",
        "window_days": 60,
        "keyword_groups": [
            [
                "friperie", "occasion", "seconde main", "vintage", "meuble",
                "reconditionné", "reconditionne", "refurbished",
            ],
            ["ticket", "facture", "total", "garantie"],
        ],
        "description_fr": "Prolongez la durée de vie des vêtements, objets et appareils par l'occasion ou le reconditionnement.",
        "tips_fr": "Le reçu ou la facture doit identifier l'article, son état d'occasion ou reconditionné, la date, le total et le vendeur.",
    },
    {
        "code": "REPAIR_RECEIPT",
        "category": "CONSUMPTION",
        "label_fr": "Réparation (vélo, appareil, vêtement...)",
        "points": 15,
        "cap_count": 4,
        "cap_period": "MONTH",
        "window_days": 30,
        "keyword_groups": [
            [
                "vélo", "velo", "bicyclette", "trottinette", "vtt",
                "réparation", "reparation", "dépannage", "depannage",
                "cordonnier",
            ],
            ["facture", "ticket", "total"],
        ],
        "description_fr": "Réparez un vélo, un appareil ou un vêtement plutôt que de le remplacer.",
        "tips_fr": "Le reçu doit décrire l'objet et la réparation, avec la date, le montant total et le nom du réparateur.",
    },
    {
        "code": "RESPONSIBLE_SHOPPING",
        "category": "CONSUMPTION",
        "label_fr": "Courses responsables (vrac, bio, producteur local)",
        "points": 10,
        "cap_count": 6,
        "cap_period": "MONTH",
        "window_days": 30,
        "keyword_groups": [
            [
                "vrac", "recharge", "zéro déchet", "zero dechet", "refill",
                "bio", "marché", "marche", "producteur", "local", "fermier",
            ],
            ["ticket", "total", "kg"],
        ],
        "description_fr": "Réduisez les emballages ou privilégiez des produits bio et des producteurs locaux.",
        "tips_fr": "Le ticket doit nommer les produits ou le marché/producteur, avec la date, le montant total et le vendeur.",
    },
    {
        "code": "TEXTILE_LABEL",
        "category": "TEXTILE",
        "label_fr": "Étiquette vêtement éthique ou recyclé",
        "points": 10,
        "cap_count": 4,
        "cap_period": "MONTH",
        "window_days": None,
        "keyword_groups": [
            ["coton bio", "organic cotton", "lin", "recyclé", "recycle", "gots", "oeko-tex"],
        ],
        "description_fr": "Montrez une étiquette indiquant une matière ou certification textile responsable.",
        "tips_fr": "Photographiez nettement l'étiquette complète et la mention de matière ou certification responsable ; aucune date n'est requise.",
    },
    {
        "code": "WORKSHOP_ATTESTATION",
        "category": "ENGAGEMENT",
        "label_fr": "Attestation d'atelier ou de formation écologique",
        "points": 30,
        "cap_count": 2,
        "cap_period": "QUARTER",
        "window_days": 90,
        "keyword_groups": [
            ["attestation", "certificat", "participation", "atelier", "formation"],
            ["environnement", "écologie", "ecologie", "climat", "durable"],
        ],
        "description_fr": "Participez à un atelier ou une formation sur l'environnement.",
        "tips_fr": "Envoyez l'attestation avec le nom de l'activité, l'organisateur et la date.",
    },
    {
        "code": "ECO_ACTION_PHOTO",
        "category": "ENGAGEMENT",
        "label_fr": "Photo d'action écologique (composteur, plantation d'arbre)",
        "points": 25,
        "cap_count": 1,
        "cap_period": "QUARTER",
        "window_days": None,
        "keyword_groups": [],
        "description_fr": "Montrez votre composteur en usage ou un arbre que vous avez planté.",
        "tips_fr": "La photo doit montrer clairement le composteur avec son contenu ou l'arbre planté dans son environnement.",
    },
]

RETIRED_PROOF_TYPE_CODES = {
    "BIKE_REPAIR",
    "LED_BULBS",
    "WATER_SAVING_DEVICE",
    "INSULATION",
    "SOLAR_EQUIPMENT",
    "EFFICIENT_APPLIANCE",
    "SECONDHAND_CLOTHES",
    "SECONDHAND_ITEM",
    "REFURBISHED_DEVICE",
    "BULK_REFILL",
    "ORGANIC_LOCAL_MARKET",
    "HOME_COMPOST_PHOTO",
    "TREE_PLANTING_PHOTO",
    "EV_CHARGE",
    "EV_PURCHASE",
    "ECO_LABEL_PRODUCT",
    "RECYCLING_DEPOSIT",
    "FOOD_DONATION",
}

PHOTO_ONLY_CODES = {
    "TEXTILE_LABEL",
    "ECO_ACTION_PHOTO",
}


class Command(BaseCommand):
    help = "Create proof types and impact factors; use --reset to restore built-in defaults."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Overwrite existing proof types and points factors with built-in defaults.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options["reset"]
        ProofType.objects.filter(code__in=RETIRED_PROOF_TYPE_CODES).update(is_active=False)
        ImpactFactor.objects.filter(
            action_type__in=[f"PROOF_{code}" for code in RETIRED_PROOF_TYPE_CODES]
        ).update(is_active=False)
        for item in PROOF_TYPES:
            code = item["code"]
            photo_only = code in PHOTO_ONLY_CODES
            defaults = {
                "category": item["category"],
                "label_fr": item["label_fr"],
                "description_fr": item["description_fr"],
                "tips_fr": item["tips_fr"],
                "icon": "camera" if photo_only else "document",
                "action_type": f"PROOF_{code}",
                "keyword_groups": [
                    {"terms": group, "required": True}
                    for group in item.get("required_keyword_groups", [])
                ] + [
                    {"terms": group, "required": False}
                    for group in item["keyword_groups"]
                ],
                "min_groups": (
                    2 if code == "ENERGY_RENOVATION"
                    else 1 if code == "TEXTILE_LABEL" or not photo_only
                    else 0
                ),
                "requires_date": not photo_only,
                "requires_amount": False,
                "window_days": item["window_days"],
                "cap_count": item["cap_count"],
                "cap_period": item["cap_period"],
                "photo_only": photo_only,
                "is_active": True,
            }
            proof_type, created = ProofType.objects.get_or_create(
                code=code,
                defaults=defaults,
            )
            if reset and not created:
                for field, value in defaults.items():
                    setattr(proof_type, field, value)
                proof_type.save(update_fields=list(defaults))

            factor_defaults = {
                "label": item["label_fr"],
                "unit": ImpactFactor.Unit.PROOF,
                "points_per_unit": item["points"],
                "co2_kg_per_unit": None,
                "is_active": True,
            }
            factor, factor_created = ImpactFactor.objects.get_or_create(
                action_type=f"PROOF_{code}",
                defaults=factor_defaults,
            )
            if reset and not factor_created:
                for field, value in factor_defaults.items():
                    setattr(factor, field, value)
                factor.save(update_fields=list(factor_defaults))

        action = "Restored" if reset else "Created or checked"
        self.stdout.write(self.style.SUCCESS(
            f"{action} {len(PROOF_TYPES)} proof types and impact factors; "
            f"retired {len(RETIRED_PROOF_TYPE_CODES)} proof types."
        ))
