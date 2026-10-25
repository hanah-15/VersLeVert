"""
PointsService — central points engine for the VersLeVert project.

Every module (waste, events, challenges, gamification) must call this service
to credit or debit points. Never create PointsTransaction objects directly.

Rules enforced here:
  BR-01: Points are always recorded via PointsTransaction (immuable).
  BR-02: Each (user, source_type, source_id, reason) is credited only once.
  BR-13: Badges are evaluated after every transaction.
  BR-17: Notifications are created for every point variation.
"""

import logging

from django.db import IntegrityError, transaction as db_transaction

logger = logging.getLogger(__name__)


class PointsService:
    """Centralised service for all point operations."""

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    @staticmethod
    def balance(user) -> int:
        """Return the current point balance for *user*.

        We read the most recent ``balance_after`` from the ledger.
        Returns 0 if the user has no transactions yet.
        """
        from ..models import PointsTransaction  # local import to avoid circular deps
        tx = (
            PointsTransaction.objects
            .filter(user=user)
            .order_by("-created_at")
            .values("balance_after")
            .first()
        )
        return tx["balance_after"] if tx else 0

    @staticmethod
    @db_transaction.atomic
    def credit(
        user,
        action_type: str,
        quantity: float = 1,
        source_type: str = "",
        source_id: int | None = None,
        reason: str = "",
    ) -> "PointsTransaction | None":
        """Credit *user* with points for *action_type*.

        Returns the new ``PointsTransaction``, or ``None`` if the
        idempotency constraint (BR-02) prevents a duplicate credit.

        Args:
            user:        The recipient user.
            action_type: Semantic label matching an ``ImpactFactor.action_type``.
            quantity:    Physical quantity (kg, count, proofs).
            source_type: E.g. "waste_collection", "eco_proof", "eco_event".
            source_id:   PK of the originating object.
            reason:      Short label for the ledger (e.g. "Collecte confirmée").
        """
        from ..models import ImpactFactor, PointsTransaction
        from accounts.models import Notification

        # Resolve factor — fall back to 1 pt/unit if not found
        try:
            factor = ImpactFactor.objects.get(action_type=action_type, is_active=True)
            pts = max(1, int(round(float(quantity) * factor.points_per_unit)))
            snapshot = {
                "action_type": factor.action_type,
                "unit": factor.unit,
                "points_per_unit": factor.points_per_unit,
                "co2_kg_per_unit": str(factor.co2_kg_per_unit),
            }
        except ImpactFactor.DoesNotExist:
            pts = max(1, int(round(float(quantity))))
            snapshot = None
            logger.warning(
                "ImpactFactor not found for action_type=%s; using raw quantity as pts.",
                action_type,
            )

        balance = PointsService.balance(user) + pts

        try:
            with db_transaction.atomic():
                tx = PointsTransaction(
                    user=user,
                    direction=PointsTransaction.Direction.CREDIT,
                    action_type=action_type,
                    quantity=quantity,
                    points=pts,
                    balance_after=balance,
                    source_type=source_type or "",
                    source_id=source_id,
                    reason=reason,
                    factor_snapshot=snapshot,
                )
                tx.save()  # triggers the immutability guard (pk check skipped on first save)
        except IntegrityError:
            # BR-02: already credited
            logger.info(
                "Duplicate credit attempt for user=%s source_type=%s source_id=%s reason=%s — skipped.",
                user.pk, source_type, source_id, reason,
            )
            return None

        # Notify user (BR-17)
        PointsService._notify(user, f"+{pts} pts — {reason or action_type}")

        # Evaluate badges (BR-13)
        PointsService._evaluate_badges(user)

        return tx

    @staticmethod
    @db_transaction.atomic
    def debit(
        user,
        amount: int,
        reason: str = "",
        source_type: str = "",
        source_id: int | None = None,
    ) -> "PointsTransaction | None":
        """Debit *amount* points from *user*.

        Returns ``None`` if the balance is insufficient.
        """
        from ..models import PointsTransaction

        current = PointsService.balance(user)
        if current < amount:
            return None

        balance = current - amount
        tx = PointsTransaction(
            user=user,
            direction=PointsTransaction.Direction.DEBIT,
            action_type="REWARD_REDEEM",
            quantity=1,
            points=-amount,
            balance_after=balance,
            source_type=source_type or "",
            source_id=source_id,
            reason=reason,
        )
        tx.save()

        PointsService._notify(user, f"−{amount} pts — {reason}")
        return tx

    @staticmethod
    @db_transaction.atomic
    def adjust(
        user,
        delta: int,
        reason: str,
        admin_user=None,
    ) -> "PointsTransaction":
        """Create an admin adjustment transaction (PT-14).

        *delta* may be positive or negative.
        The balance will never go below 0.
        """
        from ..models import PointsTransaction

        current = PointsService.balance(user)
        new_balance = max(0, current + delta)
        actual_delta = new_balance - current  # may differ from delta if floor applied

        tx = PointsTransaction(
            user=user,
            direction=PointsTransaction.Direction.ADJUSTMENT,
            action_type="ADMIN_ADJUSTMENT",
            quantity=1,
            points=actual_delta,
            balance_after=new_balance,
            reason=reason,
            source_type="admin",
            source_id=admin_user.pk if admin_user else None,
        )
        tx.save()

        sign = "+" if actual_delta >= 0 else ""
        PointsService._notify(user, f"{sign}{actual_delta} pts (ajustement) — {reason}")
        return tx

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _notify(user, message: str):
        """Create a Notification for *user* (BR-17).

        Silently swapped to a no-op if the Notification model is not
        yet ready (other modules still migrating).
        """
        try:
            from accounts.models import Notification
            Notification.objects.create(user=user, message=message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not create notification for user=%s: %s", user.pk, exc)

    @staticmethod
    def _evaluate_badges(user):
        """Award any badge whose threshold the user now meets (BR-13, PT-10).

        Evaluated entirely from PointsTransaction — never reads other models.
        """
        from ..models import Badge, PointsTransaction, UserBadge

        already_earned = set(
            UserBadge.objects.filter(user=user).values_list("badge_id", flat=True)
        )
        active_badges = Badge.objects.filter(is_active=True).exclude(pk__in=already_earned)

        for badge in active_badges:
            earned = False

            if badge.criteria_type == Badge.CriteriaType.TOTAL_POINTS:
                total = PointsService.balance(user)
                earned = total >= badge.threshold

            elif badge.criteria_type == Badge.CriteriaType.ACTION_COUNT:
                qs = PointsTransaction.objects.filter(
                    user=user,
                    direction=PointsTransaction.Direction.CREDIT,
                )
                if badge.criteria_action_type:
                    qs = qs.filter(action_type=badge.criteria_action_type)
                earned = qs.count() >= badge.threshold

            elif badge.criteria_type == Badge.CriteriaType.ACTION_QUANTITY:
                from django.db.models import Sum
                qs = PointsTransaction.objects.filter(
                    user=user,
                    direction=PointsTransaction.Direction.CREDIT,
                )
                if badge.criteria_action_type:
                    qs = qs.filter(action_type=badge.criteria_action_type)
                total_qty = qs.aggregate(s=Sum("quantity"))["s"] or 0
                earned = total_qty >= badge.threshold

            if earned:
                try:
                    UserBadge.objects.create(user=user, badge=badge)
                    PointsService._notify(user, f"Badge débloqué : {badge.icon} {badge.name} !")
                    logger.info("Badge %s awarded to user=%s", badge.code, user.pk)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not award badge %s to user=%s: %s", badge.code, user.pk, exc)
