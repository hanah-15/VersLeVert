from rest_framework import serializers
from .models import Challenge, ChallengeParticipation, ProgressEntry


class ProgressEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressEntry
        fields = ("id", "value", "note", "created_at")
        read_only_fields = ("id", "created_at")


class ChallengeParticipationSerializer(serializers.ModelSerializer):
    challenge_title = serializers.CharField(source="challenge.title", read_only=True)
    unit = serializers.CharField(source="challenge.unit", read_only=True)
    goal_value = serializers.DecimalField(source="challenge.goal_value", max_digits=10, decimal_places=2, read_only=True)
    percentage = serializers.IntegerField(read_only=True)
    is_completed = serializers.BooleanField(read_only=True)
    progress_entries = ProgressEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ChallengeParticipation
        fields = (
            "id",
            "challenge",
            "challenge_title",
            "unit",
            "goal_value",
            "progress_value",
            "percentage",
            "is_completed",
            "completed_at",
            "points_awarded",
            "joined_at",
            "progress_entries",
        )
        read_only_fields = (
            "id",
            "progress_value",
            "percentage",
            "is_completed",
            "completed_at",
            "points_awarded",
            "joined_at",
        )


class ChallengeSerializer(serializers.ModelSerializer):
    creator_username = serializers.CharField(source="created_by.username", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    participations_count = serializers.IntegerField(source="participations.count", read_only=True)
    is_joined = serializers.SerializerMethodField()

    def get_is_joined(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.participations.filter(user=request.user).exists()
        return False

    class Meta:
        model = Challenge
        fields = (
            "id",
            "title",
            "description",
            "goal_value",
            "unit",
            "challenge_type",
            "points_reward",
            "start_date",
            "end_date",
            "status",
            "is_active",
            "creator_username",
            "participations_count",
            "is_joined",
            "created_at",
        )
        read_only_fields = ("id", "creator_username", "participations_count", "is_joined", "created_at")
