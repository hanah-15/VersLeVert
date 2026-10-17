from django.contrib.auth.models import AbstractUser
from django.db import models

from config import settings
from django.conf import settings
class User(AbstractUser):
    email = models.EmailField(unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
class CollectorProfile(models.Model):
    class CollectorType(models.TextChoices):
        FARMER = "farmer", "Agriculteur"
        COOPERATIVE = "cooperative", "Coopérative"
        RECYCLING = "recycling", "Point de recyclage"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="collector_profile")
    organisation = models.CharField(max_length=150)
    type = models.CharField(max_length=15, choices=CollectorType.choices)
    accepts_organic = models.BooleanField(default=True)
    accepts_plastic = models.BooleanField(default=False)
    radius_km = models.PositiveIntegerField(default=10)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.organisation    