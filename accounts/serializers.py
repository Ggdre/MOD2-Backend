from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomerProfile, User, WorkerProfile
from services.models import ServiceCategory


class WorkerProfileSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.filter(is_active=True),
        source="category",
        required=False,
        allow_null=True,
    )
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = WorkerProfile
        fields = (
            "id",
            "category_id",
            "category_name",
            "skills",
            "is_available",
            "service_radius_km",
            "current_latitude",
            "current_longitude",
            "last_available_at",
            "average_rating",
            "total_completed_jobs",
        )
        read_only_fields = (
            "is_available",
            "current_latitude",
            "current_longitude",
            "last_available_at",
            "average_rating",
            "total_completed_jobs",
            "category_name",
        )


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        fields = ("id", "emergency_contact_name", "emergency_contact_phone", "notes")


class UserSerializer(serializers.ModelSerializer):
    worker_profile = WorkerProfileSerializer(read_only=True)
    customer_profile = CustomerProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone_number",
            "default_address",
            "default_latitude",
            "default_longitude",
            "is_email_verified",
            "worker_profile",
            "customer_profile",
        )
        read_only_fields = ("role", "is_email_verified")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Service category ID for workers (e.g., Electrician, Plumber, HVAC)",
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "role",
            "first_name",
            "last_name",
            "phone_number",
            "default_address",
            "default_latitude",
            "default_longitude",
            "category_id",
        )

    def validate_role(self, value: str) -> str:
        allowed_roles = {User.Role.CUSTOMER, User.Role.WORKER}
        if value not in allowed_roles:
            raise serializers.ValidationError(_("Registration is only available for customers or workers."))
        return value

    def create(self, validated_data: dict[str, Any]) -> User:
        category_id = validated_data.pop("category_id", None)
        password = validated_data.pop("password")
        
        # Auto-fill default_address from coordinates if address is not provided
        default_lat = validated_data.get("default_latitude")
        default_lng = validated_data.get("default_longitude")
        default_address = validated_data.get("default_address", "").strip()
        
        if (not default_address or default_address == "") and default_lat and default_lng:
            from services.utils import reverse_geocode
            try:
                lat = float(default_lat)
                lng = float(default_lng)
                geocode_result = reverse_geocode(lat, lng)
                if geocode_result.get("address"):
                    validated_data["default_address"] = geocode_result["address"]
            except (ValueError, TypeError):
                pass  # If geocoding fails, continue without address
        
        user = User.objects.create_user(password=password, **validated_data)
        
        # Set category for worker profile if provided during registration
        if user.role == User.Role.WORKER and category_id:
            profile = getattr(user, "worker_profile", None)
            if profile:
                profile.category = category_id
                profile.save(update_fields=["category"])
        
        return user


class WorkerAvailabilitySerializer(serializers.Serializer):
    is_available = serializers.BooleanField()
    current_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    current_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    service_radius_km = serializers.IntegerField(min_value=1, required=False)
    skills = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.filter(is_active=True),
        source="category",
        required=False,
        allow_null=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("is_available"):
            if "current_latitude" not in attrs or "current_longitude" not in attrs:
                raise serializers.ValidationError(_("Latitude and longitude are required when setting available."))
        return attrs

    def update(self, instance: WorkerProfile, validated_data: dict[str, Any]) -> WorkerProfile:
        is_available = validated_data["is_available"]
        latitude = validated_data.get("current_latitude")
        longitude = validated_data.get("current_longitude")
        if latitude is not None:
            latitude = float(latitude)
        if longitude is not None:
            longitude = float(longitude)
        instance.set_available(is_available, latitude=latitude, longitude=longitude)

        if "service_radius_km" in validated_data:
            instance.service_radius_km = validated_data["service_radius_km"]
        if "skills" in validated_data:
            instance.skills = validated_data["skills"]
        if "category" in validated_data:
            instance.category = validated_data["category"]
        instance.save()
        return instance


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True)

    def validate_role(self, value: str) -> str:
        allowed = {User.Role.CUSTOMER, User.Role.WORKER}
        if value not in allowed:
            raise serializers.ValidationError(_("Google login can only create customer or worker accounts."))
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        token = attrs["id_token"]
        request_obj = google_requests.Request()
        audiences = settings.GOOGLE_CLIENT_IDS or [None]
        payload = None
        errors: list[str] = []

        for audience in audiences:
            try:
                payload = id_token.verify_oauth2_token(token, request_obj, audience=audience)
                break
            except ValueError as exc:  # noqa: PERF203
                errors.append(str(exc))

        if payload is None:
            raise serializers.ValidationError({"id_token": _("Token verification failed: %s") % "; ".join(errors)})

        if settings.GOOGLE_CLIENT_IDS and payload.get("aud") not in settings.GOOGLE_CLIENT_IDS:
            raise serializers.ValidationError({"id_token": _("Token audience is not allowed.")})

        attrs["payload"] = payload
        return attrs
    def save(self, **kwargs) -> dict[str, Any]:
        payload = self.validated_data["payload"]
        email = payload.get("email")
        if not email:
            raise serializers.ValidationError({"email": _("Email not provided by Google.")})

        role = self.validated_data.get("role") or User.Role.CUSTOMER
        defaults = {
            "first_name": payload.get("given_name", ""),
            "last_name": payload.get("family_name", ""),
            "is_email_verified": payload.get("email_verified", False),
            "role": role,
            "phone_number": self.validated_data.get("phone_number", ""),
        }

        user, created = User.objects.update_or_create(
            email=email,
            defaults=defaults,
        )

        refresh = RefreshToken.for_user(user)
        data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user, context=self.context).data,
            "created": created,
        }
        return data


class AuthTokenSerializer(TokenObtainPairSerializer):
    """SimpleJWT serializer that embeds user payload."""

    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data

