from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    city = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    @property
    def is_sponsor(self):
        return getattr(self, "sponsor_account", None) is not None and self.sponsor_account.status == SponsorAccount.Status.APPROVED

    @property
    def is_admin_user(self):
        return self.is_staff or self.is_superuser


class SponsorAccount(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        SUSPENDED = "SUSPENDED", "Suspendu"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="sponsor_account")
    business_name = models.CharField(max_length=150)
    activity = models.CharField(max_length=150)
    description = models.TextField()
    logo = models.ImageField(upload_to="sponsors/", blank=True, null=True)
    contact_email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="validated_sponsors")
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def approve(self, admin_user):
        self.status = self.Status.APPROVED
        self.rejection_reason = ""
        self.validated_by = admin_user
        self.validated_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "validated_by", "validated_at"])

    def reject(self, admin_user, reason):
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.validated_by = admin_user
        self.validated_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "validated_by", "validated_at"])

    def __str__(self):
        return self.business_name


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
