from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from .forms import WasteRequestForm
from .models import WasteRequest


class MyRequestsView(LoginRequiredMixin, ListView):
    template_name = "waste/index.html"
    context_object_name = "requests"

    def get_queryset(self):
        return WasteRequest.objects.filter(user=self.request.user)


class WasteCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = WasteRequestForm
    template_name = "waste/request_form.html"
    success_url = reverse_lazy("waste:index")
    success_message = "Demande envoyée. Aucun point avant la confirmation du poids par le collecteur."

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)