"""
Contrat d'intégration pour travailler en parallèle (Section 7 du cahier de conception).
Fourni pour Marie (M2) afin que M3, M4 et M6 puissent appeler award_points().
"""
import logging

logger = logging.getLogger(__name__)


def award_points(user, source_type, source_id, base_points, impact_factor=1.0, description=""):
    """
    Crée une PointTransaction, vérifie les badges, retourne la transaction.
    Tant que M2 n'a pas finalisé ses modèles, journalise et retourne un dict descriptif.
    """
    try:
        from gamification.models import PointTransaction
        amount = int(round(base_points * impact_factor))
        tx = PointTransaction.objects.create(
            user=user,
            amount=amount,
            source_type=source_type,
            source_id=source_id,
            base_points=base_points,
            impact_factor=impact_factor,
            description=description,
        )
        return tx
    except Exception:
        # Fallback avant la migration du modèle PointTransaction de M2
        total_points = int(round(base_points * impact_factor))
        logger.info(
            "Points attribués à %s: %s (source=%s, id=%s, desc=%s)",
            user, total_points, source_type, source_id, description
        )
        return {
            "user": user,
            "source_type": source_type,
            "source_id": source_id,
            "base_points": base_points,
            "impact_factor": impact_factor,
            "amount": total_points,
            "description": description,
        }
