from django.db.models import Count, Q
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .forms import PlaceFilterForm, RecommendationFilterForm
from .models import Place, ProductRecommendation
from .services import find_places


class CataloguePagination(PageNumberPagination):
    page_size = 12


class PlaceSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    distance = serializers.FloatField(read_only=True, default=None, allow_null=True)

    class Meta:
        model = Place
        fields = ("id", "name", "category", "category_label", "description", "address", "latitude", "longitude", "distance")


class RecommendationSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    author = serializers.SerializerMethodField()

    def get_author(self, obj):
        return obj.user.first_name or obj.user.username

    class Meta:
        model = ProductRecommendation
        fields = ("id", "product_name", "category", "category_label", "description", "place", "author", "like_count", "created_at")


class PlaceListAPI(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PlaceSerializer
    pagination_class = CataloguePagination

    def get_queryset(self):
        form = PlaceFilterForm(self.request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return find_places(form.cleaned_data)


class PlaceDetailAPI(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PlaceSerializer
    queryset = Place.objects.all()


class RecommendationListAPI(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = RecommendationSerializer
    pagination_class = CataloguePagination

    def get_queryset(self):
        form = RecommendationFilterForm(self.request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        data = form.cleaned_data
        queryset = ProductRecommendation.objects.filter(status=ProductRecommendation.Status.APPROVED).select_related("user", "place").annotate(like_count=Count("likes")).order_by("-created_at", "-pk")
        if data["q"]:
            queryset = queryset.filter(Q(product_name__icontains=data["q"]) | Q(description__icontains=data["q"]))
        if data["category"]:
            queryset = queryset.filter(category=data["category"])
        if data["sort"] == "popular":
            queryset = queryset.order_by("-like_count", "-created_at", "-pk")
        return queryset


class RecommendationDetailAPI(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = RecommendationSerializer
    queryset = ProductRecommendation.objects.filter(status=ProductRecommendation.Status.APPROVED).select_related("user", "place").annotate(like_count=Count("likes"))
