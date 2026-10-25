from decimal import Decimal
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Challenge, ChallengeParticipation
from .serializers import ChallengeParticipationSerializer, ChallengeSerializer, ProgressEntrySerializer


class ChallengeListAPI(generics.ListCreateAPIView):
    """
    API: Liste des défis (filtres q, type, status) et création par le créateur.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChallengeSerializer

    def get_queryset(self):
        qs = Challenge.objects.all().select_related("created_by")
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        c_type = self.request.query_params.get("type")
        if c_type in ("points", "personnel"):
            qs = qs.filter(challenge_type=c_type)
        c_status = self.request.query_params.get("status")
        if c_status in ("active", "closed"):
            qs = qs.filter(status=c_status)
        return qs

    def perform_create(self, serializer):
        # Si utilisateur non-staff, crée un défi personnel
        c_type = serializer.validated_data.get("challenge_type", Challenge.Type.PERSONAL)
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            c_type = Challenge.Type.PERSONAL

        points = 0
        if c_type == Challenge.Type.POINTS and (self.request.user.is_staff or self.request.user.is_superuser):
            points = serializer.validated_data.get("points_reward", 0)

        challenge = serializer.save(
            created_by=self.request.user,
            challenge_type=c_type,
            points_reward=points,
        )
        if c_type == Challenge.Type.PERSONAL:
            ChallengeParticipation.objects.get_or_create(challenge=challenge, user=self.request.user)


class ChallengeDetailAPI(generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChallengeSerializer
    queryset = Challenge.objects.all().select_related("created_by")


class MyParticipationsAPI(generics.ListAPIView):
    """
    API: Liste des participations de l'utilisateur connecté.
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = ChallengeParticipationSerializer

    def get_queryset(self):
        return (
            ChallengeParticipation.objects.filter(user=self.request.user)
            .select_related("challenge")
            .prefetch_related("progress_entries")
        )


class JoinChallengeAPI(APIView):
    """
    API: Rejoindre un défi (C-02).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        try:
            challenge = Challenge.objects.get(pk=pk)
        except Challenge.DoesNotExist:
            return Response({"error": "Défi introuvable."}, status=status.HTTP_404_NOT_FOUND)

        can_join, reason = challenge.can_be_joined_by(request.user)
        if not can_join:
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

        participation = ChallengeParticipation.objects.create(challenge=challenge, user=request.user)
        serializer = ChallengeParticipationSerializer(participation, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AddProgressAPI(APIView):
    """
    API: Ajouter une progression sur une participation (C-04, C-05).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        try:
            participation = ChallengeParticipation.objects.get(pk=pk, user=request.user)
        except ChallengeParticipation.DoesNotExist:
            return Response({"error": "Participation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            val = Decimal(str(request.data.get("value", "0")))
            if val <= Decimal("0"):
                return Response({"error": "La valeur doit être strictement positive."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Format numérique invalide."}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get("note", "")
        entry, just_completed = participation.add_progress(val, note=note)

        serializer = ChallengeParticipationSerializer(participation, context={"request": request})
        return Response({
            "message": "Progression enregistrée avec succès.",
            "just_completed": just_completed,
            "participation": serializer.data,
        }, status=status.HTTP_200_OK)
