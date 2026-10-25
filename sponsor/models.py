from django.conf import settings
from django.db import models

from accounts.models import SponsorAccount


class Offer(models.Model):
    sponsor = models.ForeignKey(SponsorAccount, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=150)
    description = models.TextField()
    points_cost = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class RewardCode(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="codes")
    code = models.CharField(max_length=64, unique=True)
    redeemed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_used(self):
        return self.redeemed_at is not None
