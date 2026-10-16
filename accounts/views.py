from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import SignUpForm

from django.contrib.messages.views import SuccessMessageMixin

class SignUpView(SuccessMessageMixin, CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
    success_message = "Compte créé avec succès. Vous pouvez vous connecter."