from django.conf import settings
from django.http import HttpResponseNotFound


class ProofCameraPolicyMiddleware:
    """Allow same-origin camera access for the in-page proof capture UI."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", "camera=(self)")
        return response


class PrivateProofMediaMiddleware:
    """Prevent legacy proof uploads under MEDIA_ROOT from being served directly."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        proof_media_prefix = f"{settings.MEDIA_URL.rstrip('/')}/eco_proofs/"
        if request.path.startswith(proof_media_prefix):
            return HttpResponseNotFound()
        return self.get_response(request)
