from django.conf import settings
from django.db import models

from accounts.models import SponsorAccount


class Offer(models.Model):
    sponsor = models.ForeignKey(SponsorAccount, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=150)
    description = models.TextField()
    points_cost = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to="offers/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    images_url = models.TextField(blank=True, null=True, help_text="JSON array of image URLs or newline-separated URLs")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def image_list(self):
        urls = []
        if self.image:
            try:
                urls.append(self.image.url)
            except Exception:
                pass
        if self.image_url:
            urls.append(self.image_url.strip())
        if self.images_url:
            import json
            raw = self.images_url.strip()
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    for u in data:
                        if isinstance(u, str) and u.strip():
                            urls.append(u.strip())
            except Exception:
                for line in raw.replace(',', '\n').splitlines():
                    line = line.strip()
                    if line and line.startswith('http'):
                        urls.append(line)
        # deduplicate while preserving order
        seen = set()
        out = []
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    @property
    def primary_image_url(self):
        lst = self.image_list
        return lst[0] if lst else None


class RewardCode(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="codes")
    code = models.CharField(max_length=64, unique=True)
    redeemed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_used(self):
        return self.used_at is not None
