from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.core.exceptions import ValidationError
from .models import User
from .models import SponsorAccount

class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


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