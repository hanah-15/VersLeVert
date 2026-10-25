from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import SponsorAccount, User


AUTH_INPUT_CLASSES = (
    "w-full rounded-2xl border border-white/40 bg-white/30 px-5 py-3.5 "
    "text-forest placeholder:text-forest/50 backdrop-blur-md transition-all "
    "duration-500 hover:border-palm/50 focus:border-palm focus:bg-white/45 "
    "focus:outline-none focus:ring-4 focus:ring-palm/30"
)


class VersLeVertAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "auth-input " + AUTH_INPUT_CLASSES
            if field.widget.input_type == "password":
                field.widget.attrs["class"] += " pr-14"


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "auth-input " + AUTH_INPUT_CLASSES
            if field.widget.input_type == "password":
                field.widget.attrs["class"] += " pr-14"


class SponsorApplicationForm(forms.ModelForm):
    class Meta:
        model = SponsorAccount
        fields = ("business_name", "activity", "contact_email", "phone", "description")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("avatar", "first_name", "last_name", "city")
        widgets = {"avatar": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"})}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            if avatar.size > 2 * 1024 * 1024:
                raise ValidationError("La photo ne doit pas dépasser 2 Mo.")
            if avatar.content_type not in {"image/jpeg", "image/png"}:
                raise ValidationError("La photo doit être au format JPG ou PNG.")
        return avatar