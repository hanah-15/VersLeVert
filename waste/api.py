from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .ai.advice import get_or_create_advice
from .models import EcoAdvice


class EcoAdviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EcoAdvice
        fields = ("payload", "source", "grounded", "duration_ms", "created_at")
        read_only_fields = fields


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def advice_view(request):
    if request.method == "GET":
        advice = EcoAdvice.objects.filter(user=request.user).first()
        if advice is None:
            return Response({"detail": "Aucun bilan éco n'est encore disponible."}, status=404)
    else:
        advice = get_or_create_advice(request.user)
    return Response(EcoAdviceSerializer(advice).data)
