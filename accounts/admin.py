from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import get_object_or_404, redirect
from django import forms
from .models import Notification, SponsorAccount, User

admin.site.register(User, UserAdmin)


class RejectionForm(forms.Form):
    reason = forms.CharField(label="Motif du rejet", widget=forms.Textarea)


@admin.register(SponsorAccount)
class SponsorAccountAdmin(admin.ModelAdmin):
    list_display = ("business_name", "user", "status", "validated_by", "validated_at", "created_at")
    list_filter = ("status",)
    search_fields = ("business_name", "user__email")
    readonly_fields = ("validated_by", "validated_at", "created_at")
    actions = ("approve_applications", "reject_applications")

    @admin.action(description="Approuver")
    def approve_applications(self, request, queryset):
        for account in queryset:
            account.approve(request.user)
            Notification.objects.create(user=account.user, message="Votre demande sponsor a été approuvée.")
            self.message_user(request, f"{account.business_name} approuvé.", messages.SUCCESS)

    @admin.action(description="Rejeter (motif obligatoire)")
    def reject_applications(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez une seule demande pour la rejeter.", messages.ERROR)
            return
        account = queryset.first()
        return redirect(reverse("admin:accounts_sponsoraccount_reject", args=[account.pk]))

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<path:object_id>/reject/", self.admin_site.admin_view(self.reject_view), name="accounts_sponsoraccount_reject"),
        ]
        return custom + urls

    def reject_view(self, request, object_id):
        account = get_object_or_404(SponsorAccount, pk=object_id)
        if request.method == "POST":
            form = RejectionForm(request.POST)
            if form.is_valid():
                account.reject(request.user, form.cleaned_data["reason"])
                Notification.objects.create(
                    user=account.user,
                    message=f"Votre demande sponsor a été rejetée : {account.rejection_reason}",
                )
                self.message_user(request, "Demande rejetée.", messages.SUCCESS)
                return redirect("admin:accounts_sponsoraccount_changelist")
        else:
            form = RejectionForm()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Rejeter la demande",
            "form": form,
            "account": account,
        }
        return TemplateResponse(request, "admin/sponsor_reject.html", context)