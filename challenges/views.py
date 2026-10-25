from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from .forms import (
    AdminChallengeForm,
    ChallengeFilterForm,
    PersonalChallengeForm,
    ProgressEntryForm,
)
from .ai import GroqUnavailableError, recommend_challenges
from .models import (
    Challenge,
    ChallengeMilestone,
    ChallengeParticipation,
    ChallengeReminder,
    ProgressEntry,
)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_staff or self.request.user.is_superuser
        )


class ChallengeListView(LoginRequiredMixin, ListView):
    """
    Catalogue des défis (C-01, T-02).
    Affiche la liste des défis avec titre, objectif, points, période.
    """
    model = Challenge
    template_name = "challenges/index.html"
    context_object_name = "challenges"
    paginate_by = 4

    def get_queryset(self):
        qs = Challenge.objects.select_related("created_by").annotate(
            participants_count=Count("participations")
        )
        self.filter_form = ChallengeFilterForm(self.request.GET)
        if self.filter_form.is_valid():
            q = self.filter_form.cleaned_data.get("q")
            if q:
                qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
            c_type = self.filter_form.cleaned_data.get("challenge_type")
            if c_type:
                qs = qs.filter(challenge_type=c_type)
            status_val = self.filter_form.cleaned_data.get("status")
            if status_val:
                qs = qs.filter(status=status_val)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = getattr(self, "filter_form", ChallengeFilterForm())
        context["active_tab"] = "catalog"
        pagination_query = self.request.GET.copy()
        pagination_query.pop("page", None)
        context["pagination_query"] = pagination_query.urlencode()

        # Index des participations de l'utilisateur connecté
        user_participations = ChallengeParticipation.objects.filter(
            user=self.request.user
        ).select_related("challenge")
        context["user_participations_map"] = {
            p.challenge_id: p for p in user_participations
        }
        context["my_active_count"] = user_participations.filter(completed_at__isnull=True).count()
        context["my_completed_count"] = user_participations.filter(completed_at__isnull=False).count()
        context["reminders"] = ChallengeReminder.objects.filter(
            user=self.request.user, enabled=True
        ).values_list("challenge_id", flat=True)
        return context


class MyChallengesView(LoginRequiredMixin, ListView):
    """
    Mes défis (actifs et terminés) avec barres de progression (C-04).
    """
    model = ChallengeParticipation
    template_name = "challenges/my_challenges.html"
    context_object_name = "participations"

    def get_queryset(self):
        return (
            ChallengeParticipation.objects.filter(user=self.request.user)
            .select_related("challenge", "challenge__created_by")
            .order_by("completed_at", "-joined_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "mine"
        participations = list(self.get_queryset())
        active_participations = [p for p in participations if not p.completed_at]
        context["completed_participations"] = [p for p in participations if p.completed_at]
        active_paginator = Paginator(active_participations, 4)
        active_page_number = self.request.GET.get("active_page", 1)
        context["active_page_obj"] = active_paginator.get_page(active_page_number)
        context["active_paginator"] = active_paginator
        context["active_participations"] = context["active_page_obj"].object_list
        context["active_is_paginated"] = active_paginator.num_pages > 1
        return context


class ChallengeDetailView(LoginRequiredMixin, DetailView):
    """
    Détail d'un défi, visualisation de la progression personnelle et ajout d'étape.
    """
    model = Challenge
    template_name = "challenges/detail.html"
    context_object_name = "challenge"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        challenge = self.get_object()
        user_participation = ChallengeParticipation.objects.filter(
            challenge=challenge, user=self.request.user
        ).first()

        context["user_participation"] = user_participation
        context["progress_form"] = ProgressEntryForm()
        can_join, join_reason = challenge.can_be_joined_by(self.request.user)
        context["can_join"] = can_join
        context["join_reason"] = join_reason
        context["community_total"] = (
            challenge.participations.aggregate(total=Sum("progress_value"))["total"] or 0
            if challenge.is_community
            else None
        )
        context["community_participants"] = (
            challenge.participations.count() if challenge.is_community else 0
        )
        context["milestones"] = challenge.milestones.all()
        context["reminder_enabled"] = ChallengeReminder.objects.filter(
            user=self.request.user, challenge=challenge, enabled=True
        ).exists()
        context["recent_entries"] = (
            user_participation.progress_entries.all()[:10]
            if user_participation
            else []
        )
        return context


class JoinChallengeView(LoginRequiredMixin, View):
    """
    Rejoindre un défi à points ou public (C-02).
    Un défi ne peut être rejoint qu'une fois.
    """
    def post(self, request, pk):
        challenge = get_object_or_404(Challenge, pk=pk)
        can_join, reason = challenge.can_be_joined_by(request.user)
        if not can_join:
            messages.warning(request, reason)
            return redirect(challenge.get_absolute_url())

        ChallengeParticipation.objects.create(challenge=challenge, user=request.user)
        from accounts.models import Notification

        Notification.objects.create(
            user=request.user,
            message=f"Vous avez rejoint le défi « {challenge.title} ».",
        )
        messages.success(request, f"Super ! Vous avez rejoint le défi « {challenge.title} ».")
        return redirect(challenge.get_absolute_url())


class PersonalChallengeCreateView(LoginRequiredMixin, CreateView):
    """
    Création d'un défi personnel (C-03).
    Objectif et unité obligatoires, aucun point attribué.
    L'utilisateur est immédiatement inscrit comme participant à son propre défi.
    """
    model = Challenge
    form_class = PersonalChallengeForm
    template_name = "challenges/personal_create.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.challenge_type = Challenge.Type.PERSONAL
        form.instance.points_reward = 0
        form.instance.status = Challenge.Status.ACTIVE
        response = super().form_valid(form)

        # Inscription automatique de l'auteur
        ChallengeParticipation.objects.create(
            challenge=self.object,
            user=self.request.user,
        )
        messages.success(
            self.request,
            f"Votre défi personnel « {self.object.title} » a été créé avec succès !"
        )
        return response

    def get_success_url(self):
        return reverse("challenges:detail", args=[self.object.pk])


class AddProgressView(LoginRequiredMixin, View):
    """
    Enregistrement de progression sur un défi (C-04, C-05, T-03).
    Mise à jour de la barre et attribution unique des points via M2 si objectif atteint.
    """
    def post(self, request, pk):
        challenge = get_object_or_404(Challenge, pk=pk)
        participation = get_object_or_404(
            ChallengeParticipation, challenge=challenge, user=request.user
        )

        form = ProgressEntryForm(request.POST)
        if not form.is_valid():
            for error_list in form.errors.values():
                for err in error_list:
                    messages.error(request, err)
            return redirect(challenge.get_absolute_url())

        value = form.cleaned_data["value"]
        note = form.cleaned_data.get("note", "")

        entry, just_completed = participation.add_progress(value, note=note)

        if just_completed:
            if challenge.challenge_type == Challenge.Type.POINTS and challenge.points_reward > 0:
                messages.success(
                    request,
                    f"Bravo ! Objectif atteint ({participation.progress_value} / {challenge.goal_value} {challenge.unit}). "
                    f"Vous avez remporté {challenge.points_reward} points !",
                )
            else:
                messages.success(
                    request,
                    f"Félicitations ! Vous avez accompli votre objectif ({participation.progress_value} / {challenge.goal_value} {challenge.unit}) !",
                )
        else:
            messages.success(
                request,
                f"Progression enregistrée : +{value} {challenge.unit} "
                f"({participation.progress_value} / {challenge.goal_value} {challenge.unit} · {participation.percentage}%).",
            )

        return redirect(challenge.get_absolute_url())


class AdminChallengeCreateView(StaffRequiredMixin, CreateView):
    """
    Création d'un défi à points par un administrateur (C-06).
    """
    model = Challenge
    form_class = AdminChallengeForm
    template_name = "challenges/admin_create.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.challenge_type = Challenge.Type.POINTS
        response = super().form_valid(form)
        messages.success(self.request, f"Le défi « {self.object.title} » a été publié avec succès.")
        return response

    def get_success_url(self):
        return reverse("challenges:detail", args=[self.object.pk])


class AdminCloseChallengeView(StaffRequiredMixin, View):
    """
    Clôture d'un défi par un administrateur (C-06).
    """
    def post(self, request, pk):
        challenge = get_object_or_404(Challenge, pk=pk)
        challenge.status = Challenge.Status.CLOSED
        challenge.save(update_fields=["status", "updated_at"])
        messages.info(request, f"Le défi « {challenge.title} » a été clôturé.")
        return redirect(challenge.get_absolute_url())


class ToggleChallengeReminderView(LoginRequiredMixin, View):
    def post(self, request, pk):
        challenge = get_object_or_404(Challenge, pk=pk)
        reminder, created = ChallengeReminder.objects.get_or_create(
            user=request.user,
            challenge=challenge,
            defaults={"frequency": ChallengeReminder.Frequency.WEEKLY},
        )
        reminder.enabled = not reminder.enabled if not created else True
        reminder.save(update_fields=["enabled"])
        messages.success(
            request,
            "Rappel activé." if reminder.enabled else "Rappel désactivé.",
        )
        return redirect(challenge.get_absolute_url())


class ChallengeDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "challenges/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        participations = ChallengeParticipation.objects.filter(
            user=self.request.user
        ).select_related("challenge")
        active = participations.filter(completed_at__isnull=True)
        completed = participations.filter(completed_at__isnull=False)
        context.update(
            active_tab="dashboard",
            active_participations=active,
            completed_participations=completed,
            total_progress=participations.aggregate(total=Sum("progress_value"))["total"] or 0,
            total_points=sum(
                p.challenge.points_reward for p in completed
                if p.challenge.challenge_type == Challenge.Type.POINTS
            ),
            recent_notifications=self.request.user.notifications.order_by("-created_at")[:5],
            reminders=ChallengeReminder.objects.filter(
                user=self.request.user, enabled=True
            ).select_related("challenge"),
            milestones=ChallengeMilestone.objects.filter(
                challenge__participations__user=self.request.user
            ).distinct(),
        )
        return context


class ChallengeLeaderboardView(LoginRequiredMixin, TemplateView):
    template_name = "challenges/leaderboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = (
            ChallengeParticipation.objects.values(
                "user_id", "user__username", "user__first_name", "user__last_name"
            )
            .annotate(
                completed_count=Count("id", filter=Q(completed_at__isnull=False)),
                progress_total=Sum("progress_value"),
            )
            .order_by("-completed_count", "-progress_total", "user__username")[:50]
        )
        context.update(active_tab="leaderboard", leaderboard=rows)
        return context


class ChallengeAdminStatsView(StaffRequiredMixin, TemplateView):
    template_name = "challenges/admin_stats.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        challenges = Challenge.objects.all()
        participations = ChallengeParticipation.objects.all()
        context.update(
            active_tab="admin-stats",
            total_challenges=challenges.count(),
            active_challenges=challenges.filter(status=Challenge.Status.ACTIVE).count(),
            community_challenges=challenges.filter(is_community=True).count(),
            total_participations=participations.count(),
            completed_participations=participations.filter(
                completed_at__isnull=False
            ).count(),
            total_progress=participations.aggregate(total=Sum("progress_value"))["total"] or 0,
            popular_challenges=challenges.annotate(
                participation_count=Count("participations")
            ).order_by("-participation_count", "-created_at")[:8],
        )
        return context


class ChallengeRecommendationsView(LoginRequiredMixin, TemplateView):
    template_name = "challenges/recommendations.html"

    def post(self, request, *args, **kwargs):
        active_challenges = list(
            Challenge.objects.filter(status=Challenge.Status.ACTIVE)
            .select_related("created_by")
            .prefetch_related("participations")
            .order_by("-created_at")[:30]
        )
        user_participations = ChallengeParticipation.objects.filter(
            user=request.user
        ).select_related("challenge")
        profile = {
            "completed_challenges": user_participations.filter(
                completed_at__isnull=False
            ).count(),
            "active_challenges": user_participations.filter(
                completed_at__isnull=True
            ).count(),
            "units_used": list(
                user_participations.values_list("challenge__unit", flat=True).distinct()
            ),
        }
        try:
            recommendation = recommend_challenges(profile, active_challenges)
        except GroqUnavailableError as exc:
            error_message = str(exc)
            messages.error(request, error_message)
            recommendation = ""
        else:
            error_message = ""
        return self.render_to_response(
            self.get_context_data(
                recommendation=recommendation,
                recommendation_error=error_message,
                recommendation_requested=True,
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "recommendations"
        return context