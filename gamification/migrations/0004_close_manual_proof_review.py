from django.db import migrations


TEXTILE_KEYWORDS = [
    {
        "terms": [
            "coton bio",
            "organic cotton",
            "lin",
            "recyclé",
            "recycle",
            "gots",
            "oeko-tex",
        ],
        "required": False,
    },
]


def close_manual_review_queue(apps, schema_editor):
    EcoProof = apps.get_model("gamification", "EcoProof")
    ProofType = apps.get_model("gamification", "ProofType")
    database = schema_editor.connection.alias

    EcoProof.objects.using(database).filter(status="NEEDS_REVIEW").update(
        status="REJECTED",
        rejection_code="AUTO_REVIEW_DISABLED",
        rejection_reason_fr=(
            "La preuve n'a pas pu être validée automatiquement. "
            "Vérifiez-la puis soumettez une nouvelle photo."
        ),
    )

    textile_type = ProofType.objects.using(database).filter(code="TEXTILE_LABEL").first()
    if (
        textile_type
        and textile_type.min_groups == 0
        and textile_type.keyword_groups == TEXTILE_KEYWORDS
    ):
        textile_type.min_groups = 1
        textile_type.save(update_fields=["min_groups"])


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0003_ocranalysis_error_code_ocranalysis_fallback_chain_and_more"),
    ]

    operations = [
        migrations.RunPython(close_manual_review_queue, migrations.RunPython.noop),
    ]
