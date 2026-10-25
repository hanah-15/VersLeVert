import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
)

from core.permissions import AdminRequiredMixin

from .ai import (
    generate_event_proposal_ai,
    analyze_environmental_impact_ai,
    generate_social_media_kit_ai,
    moderate_event_ai,
    generate_text,
)
from .forms import EventCloseResultForm, EventProposalForm
from .models import Event, EventRegistration
from .weather import WeatherUnavailableError, get_event_forecast


class EventListView(ListView):
    model = Event
    template_name = "events/upcoming.html"
    context_object_name = "events"

    def get_queryset(self):
        qs = Event.objects.filter(
            status=Event.Status.PUBLISHED,
            date__gt=timezone.now(),
        ).select_related("organizer").prefetch_related("registrations").order_by("date")

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(location__icontains=query)
                | Q(objective__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "").strip()
        return context


class MyEventsView(LoginRequiredMixin, TemplateView):
    template_name = "events/mine.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["organized_events"] = (
            Event.objects.filter(organizer=user)
            .prefetch_related("registrations")
            .order_by("-date")
        )
        context["my_registrations"] = (
            EventRegistration.objects.filter(user=user)
            .select_related("event", "event__organizer")
            .order_by("-event__date")
        )
        if user.is_staff or user.is_superuser or getattr(user, "is_admin_user", False):
            context["pending_events"] = (
                Event.objects.filter(status=Event.Status.PENDING)
                .select_related("organizer")
                .order_by("date")
            )
        return context


class EventResultsView(ListView):
    model = Event
    template_name = "events/results.html"
    context_object_name = "closed_events"

    def get_queryset(self):
        return (
            Event.objects.filter(status=Event.Status.CLOSED)
            .select_related("organizer")
            .prefetch_related("registrations")
            .order_by("-closed_at", "-date")
        )


class EventDetailView(DetailView):
    model = Event
    template_name = "events/detail.html"
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        event = self.object

        is_admin = user.is_authenticated and (
            user.is_staff or user.is_superuser or getattr(user, "is_admin_user", False)
        )
        is_organizer = user.is_authenticated and (user == event.organizer)

        user_registration = None
        if user.is_authenticated:
            user_registration = event.registrations.filter(user=user).first()

        context["is_organizer"] = is_organizer
        context["is_admin"] = is_admin
        context["can_manage"] = is_organizer or is_admin
        context["user_registration"] = user_registration
        context["is_registered"] = user_registration is not None
        context["can_register"] = event.can_register(user)
        context["can_unregister"] = event.can_unregister(user)
        context["can_confirm_attendance"] = (
            event.is_past
            and (is_organizer or is_admin)
            and event.status in [Event.Status.PUBLISHED, Event.Status.CLOSED]
        )
        context["can_close"] = (
            event.is_past
            and (is_organizer or is_admin)
            and event.status == Event.Status.PUBLISHED
        )
        if is_organizer or is_admin:
            context["registrations"] = (
                event.registrations.select_related("user").order_by("registered_at")
            )
        return context


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventProposalForm
    template_name = "events/form.html"

    def form_valid(self, form):
        user = self.request.user
        event = form.save(commit=False)
        event.organizer = user

        # E-02 : Événement admin publié immédiatement
        if user.is_staff or user.is_superuser or getattr(user, "is_admin_user", False):
            event.status = Event.Status.PUBLISHED
            event.save()
            messages.success(
                self.request,
                "Votre événement a été créé et publié immédiatement.",
            )
        else:
            # E-01 : Date dans le futur. Statut « en attente ».
            event.status = Event.Status.PENDING
            event.save()
            messages.success(
                self.request,
                "Votre proposition d'événement a bien été enregistrée. Elle sera visible une fois validée par un administrateur.",
            )
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventRegisterView(LoginRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        try:
            event.register(request.user)
            messages.success(request, f"Vous êtes bien inscrit à l'événement « {event.title} » !")
        except ValidationError as e:
            messages.error(request, e.message)
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventUnregisterView(LoginRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        try:
            event.unregister(request.user)
            messages.success(request, "Votre inscription a bien été annulée.")
        except ValidationError as e:
            messages.error(request, e.message)
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventAttendanceView(LoginRequiredMixin, View):
    template_name = "events/attendance.html"

    def _check_permission(self, event, user):
        is_admin = user.is_staff or user.is_superuser or getattr(user, "is_admin_user", False)
        if user != event.organizer and not is_admin:
            raise PermissionDenied("Seul l'organisateur ou un administrateur peut gérer les présences.")

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        self._check_permission(event, request.user)

        # E-04 : Possible seulement après la date
        if not event.is_past:
            messages.error(
                request,
                "La confirmation des présences n'est possible qu'après la date de l'événement.",
            )
            return redirect(reverse("events:detail", kwargs={"pk": event.pk}))

        registrations = event.registrations.select_related("user").order_by("user__first_name")
        return TemplateView.response_class(
            request=request,
            template=self.template_name,
            context={
                "event": event,
                "registrations": registrations,
            },
        )

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        self._check_permission(event, request.user)

        if not event.is_past:
            messages.error(
                request,
                "La confirmation des présences n'est possible qu'après la date de l'événement.",
            )
            return redirect(reverse("events:detail", kwargs={"pk": event.pk}))

        present_user_ids = request.POST.getlist("present_user_ids")
        try:
            event.confirm_attendance(present_user_ids=present_user_ids, by_user=request.user)
            messages.success(request, "Les présences des inscrits ont été enregistrées avec succès.")
        except ValidationError as e:
            messages.error(request, e.message)
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventCloseView(LoginRequiredMixin, View):
    template_name = "events/close.html"

    def _check_permission(self, event, user):
        is_admin = user.is_staff or user.is_superuser or getattr(user, "is_admin_user", False)
        if user != event.organizer and not is_admin:
            raise PermissionDenied("Seul l'organisateur ou un administrateur peut clôturer cet événement.")

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        self._check_permission(event, request.user)

        if not event.is_past:
            messages.error(
                request,
                "Un événement ne peut être clôturé qu'après sa date de tenue.",
            )
            return redirect(reverse("events:detail", kwargs={"pk": event.pk}))

        confirmed_count = event.registrations.filter(present=True).count()
        form = EventCloseResultForm(
            instance=event,
            initial={"actual_participants_count": confirmed_count},
        )
        return TemplateView.response_class(
            request=request,
            template=self.template_name,
            context={
                "event": event,
                "form": form,
                "confirmed_count": confirmed_count,
            },
        )

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        self._check_permission(event, request.user)

        if not event.is_past:
            messages.error(
                request,
                "Un événement ne peut être clôturé qu'après sa date de tenue.",
            )
            return redirect(reverse("events:detail", kwargs={"pk": event.pk}))

        form = EventCloseResultForm(request.POST, instance=event)
        if form.is_valid():
            cleaned = form.cleaned_data
            try:
                event.close_and_award_points(
                    collected_quantity=cleaned.get("collected_quantity", ""),
                    participants_count=cleaned.get("actual_participants_count"),
                    result_summary=cleaned.get("result_summary", ""),
                    by_user=request.user,
                )
                messages.success(
                    request,
                    "L'événement est clôturé ! Les points ont été attribués aux participants confirmés et le résultat est désormais public.",
                )
                return redirect(reverse("events:detail", kwargs={"pk": event.pk}))
            except ValidationError as e:
                messages.error(request, e.message)

        return TemplateView.response_class(
            request=request,
            template=self.template_name,
            context={
                "event": event,
                "form": form,
                "confirmed_count": event.registrations.filter(present=True).count(),
            },
        )


class AdminEventValidateView(AdminRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        event.status = Event.Status.PUBLISHED
        event.save(update_fields=["status"])
        messages.success(request, f"L'événement « {event.title} » a été validé et publié.")
        next_url = request.POST.get("next") or reverse("events:mine")
        return redirect(next_url)


class AdminEventRefuseView(AdminRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        event.status = Event.Status.REFUSED
        event.save(update_fields=["status"])
        messages.warning(request, f"L'événement « {event.title} » a été refusé.")
        next_url = request.POST.get("next") or reverse("events:mine")
        return redirect(next_url)


class EventCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        is_admin = request.user.is_staff or request.user.is_superuser or getattr(request.user, "is_admin_user", False)
        if request.user != event.organizer and not is_admin:
            raise PermissionDenied("Vous n'avez pas le droit d'annuler cet événement.")
        event.status = Event.Status.CANCELLED
        event.save(update_fields=["status"])
        messages.info(request, f"L'événement « {event.title} » a été annulé.")
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventAICopilotView(LoginRequiredMixin, View):
    """Générateur IA de proposition d'événement (titre, objectif, checklist, capacité)."""
    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            body = {}
        topic = body.get("topic") or request.POST.get("topic", "").strip()
        location = body.get("location") or request.POST.get("location", "").strip()

        if not topic:
            return JsonResponse({"error": "Veuillez fournir une idée ou un mot-clé pour l'événement."}, status=400)

        result = generate_event_proposal_ai(topic, location)
        return JsonResponse(result)


class EventAIImpactView(LoginRequiredMixin, View):
    """Calcule et renvoie l'analyse d'impact environnemental IA (CO2, équivalences) d'un événement."""
    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        if not event.ai_impact_analysis:
            data = event.generate_impact_report_ai()
        else:
            data = event.impact_analysis_dict
        return JsonResponse(data or {})

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        data = event.generate_impact_report_ai()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(data)
        messages.success(request, "L'impact écologique a été réévalué par l'IA avec succès.")
        return redirect(reverse("events:detail", kwargs={"pk": event.pk}))


class EventAISocialKitView(LoginRequiredMixin, View):
    """Génère un kit réseaux sociaux (Instagram, X, presse) pour valoriser l'événement."""
    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        kit = generate_social_media_kit_ai(event)
        return JsonResponse(kit)


class EventAIModerateView(AdminRequiredMixin, View):
    """Assistance IA à la modération pour les administrateurs."""
    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        data = event.generate_moderation_ai()
        return JsonResponse(data)


class EventAISmartSearchView(View):
    """Recherche sémantique et recommandation intelligente d'événements à venir."""
    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            body = {}
        user_query = body.get("query") or request.POST.get("query", "").strip()
        if not user_query:
            return JsonResponse({"error": "Veuillez poser une question ou décrire ce que vous recherchez."}, status=400)

        upcoming_events = list(
            Event.objects.filter(
                status=Event.Status.PUBLISHED,
                date__gt=timezone.now(),
            ).order_by("date")[:15]
        )

        if not upcoming_events:
            return JsonResponse({
                "summary": "Il n'y a actuellement aucun événement à venir disponible dans le catalogue.",
                "recommendations": [],
            })

        events_summary = [
            {
                "id": e.pk,
                "title": e.title,
                "location": e.location,
                "date": e.date.strftime("%d/%m/%Y %H:%M"),
                "objective": e.objective[:200],
                "spots": e.available_spots,
            }
            for e in upcoming_events
        ]

        prompt = (
            "Tu es le conseiller écologique personnalisé de VersLeVert. "
            "Recommande les événements les plus pertinents de la liste suivante en fonction du souhait de l'utilisateur. "
            "Réponds exclusivement avec un objet JSON valide de la forme suivante :\n"
            "{\n"
            '  "summary": "Explication conviviale et personnalisée en 2 phrases",\n'
            '  "recommendations": [\n'
            '    {"id": 1, "match_reason": "Pourquoi cet événement correspond parfaitement"}\n'
            '  ]\n'
            "}\n\n"
            f"Souhait citoyen: {user_query}\n"
            f"Événements disponibles: {json.dumps(events_summary, ensure_ascii=False)}\n"
        )

        try:
            raw = generate_text(prompt, max_output_tokens=1000)
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
            data = json.loads(raw)
            return JsonResponse(data)
        except Exception:
            q_lower = user_query.lower()
            matched = []
            for e in upcoming_events:
                if any(w in e.title.lower() or w in e.location.lower() or w in e.objective.lower() for w in q_lower.split() if len(w) > 3):
                    matched.append({"id": e.pk, "match_reason": f"Correspond aux termes recherchés : {e.title} à {e.location}"})
            if not matched and upcoming_events:
                matched.append({"id": upcoming_events[0].pk, "match_reason": "Événement le plus proche en date qui pourrait vous intéresser"})
            return JsonResponse({
                "summary": "Voici les actions citoyennes les plus proches de vos envies écologiques :",
                "recommendations": matched[:3],
            })


class EventWeatherView(View):
    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk, status=Event.Status.PUBLISHED)
        try:
            return JsonResponse(get_event_forecast(event))
        except WeatherUnavailableError as exc:
            return JsonResponse({"available": False, "message": str(exc)}, status=503)
