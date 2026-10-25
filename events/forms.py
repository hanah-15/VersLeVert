from django import forms
from django.utils import timezone
from .models import Event, EventRegistration


class EventProposalForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "objective", "location", "date", "capacity", "ai_checklist"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "ui-input input",
                    "placeholder": "Ex : Nettoyage de la plage de La Marsa",
                }
            ),
            "objective": forms.Textarea(
                attrs={
                    "class": "ui-input input",
                    "rows": 4,
                    "placeholder": "Ex : Ramasser les plastiques, sensibiliser les riverains et trier les déchets.",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "ui-input input",
                    "placeholder": "Ex : Plage de La Marsa, près du café du bord de mer",
                }
            ),
            "date": forms.DateTimeInput(
                attrs={
                    "class": "ui-input input",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "capacity": forms.NumberInput(
                attrs={
                    "class": "ui-input input",
                    "placeholder": "Laisser vide si illimité (ex : 30)",
                    "min": 1,
                }
            ),
            "ai_checklist": forms.HiddenInput(),
        }
        labels = {
            "title": "Titre",
            "objective": "Objectif de l'événement",
            "location": "Lieu de rendez-vous",
            "date": "Date et heure",
            "capacity": "Capacité maximale (optionnelle)",
        }
        help_texts = {
            "objective": "Décrivez le but écologique, le matériel à apporter, et le déroulement.",
            "capacity": "Nombre maximum de participants (optionnel). Laissez vide si sans limite.",
        }

    def clean_date(self):
        date = self.cleaned_data.get("date")
        if date and date <= timezone.now():
            raise forms.ValidationError("La date de l'événement doit être dans le futur.")
        return date

    def clean_capacity(self):
        capacity = self.cleaned_data.get("capacity")
        if capacity is not None and capacity <= 0:
            raise forms.ValidationError("La capacité doit être un nombre strictement positif.")
        return capacity


class EventCloseResultForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["collected_quantity", "actual_participants_count", "result_summary"]
        widgets = {
            "collected_quantity": forms.TextInput(
                attrs={
                    "class": "ui-input input",
                    "placeholder": "Ex : 45 kg de plastique, 30 sacs récoltés, 50 arbres plantés",
                }
            ),
            "actual_participants_count": forms.NumberInput(
                attrs={
                    "class": "ui-input input",
                    "placeholder": "Nombre de participants présents",
                    "min": 0,
                }
            ),
            "result_summary": forms.Textarea(
                attrs={
                    "class": "ui-input input",
                    "rows": 4,
                    "placeholder": "Bilan de l'action, retours des participants, points forts...",
                }
            ),
        }
        labels = {
            "collected_quantity": "Quantité collectée ou impact mesuré",
            "actual_participants_count": "Nombre de participants réels",
            "result_summary": "Compte-rendu et remarques",
        }
        help_texts = {
            "collected_quantity": "Indiquez l'impact concret de l'événement (poids de déchets, plantations, etc.).",
            "actual_participants_count": "Optionnel : sera automatiquement calculé à partir des présences cochées si laissé vide.",
        }
