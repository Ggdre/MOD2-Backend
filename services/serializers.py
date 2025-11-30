from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F
from rest_framework import serializers

from accounts.models import User, WorkerProfile
from accounts.serializers import UserSerializer
from notifications.utils import notify_request_cancelled, notify_request_completed, notify_workers_of_request
from .models import RequestActivity, ServiceCategory, ServiceRequest


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "description", "is_active")


class RequestActivitySerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = RequestActivity
        fields = ("id", "actor", "message", "created_at")


class ServiceRequestSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    worker = UserSerializer(read_only=True)
    category = ServiceCategorySerializer(read_only=True)
    distance_km = serializers.SerializerMethodField()
    activities = RequestActivitySerializer(read_only=True, many=True)
    worker_location = serializers.SerializerMethodField()
    worker_distance_km = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = (
            "id",
            "reference_code",
            "title",
            "description",
            "customer",
            "worker",
            "category",
            "status",
            "priority",
            "location_latitude",
            "location_longitude",
            "address",
            "postcode",
            "scheduled_start",
            "accepted_at",
            "completed_at",
            "cancelled_at",
            "customer_notes",
            "admin_notes",
            "estimated_duration_minutes",
            "created_at",
            "updated_at",
            "distance_km",
            "activities",
            "worker_location",
            "worker_distance_km",
        )
        read_only_fields = (
            "reference_code",
            "customer",
            "worker",
            "status",
            "accepted_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "distance_km",
            "activities",
            "worker_location",
            "worker_distance_km",
        )

    def get_distance_km(self, obj: ServiceRequest) -> float | None:
        distance_map: dict[int, float] = self.context.get("distance_map", {})
        distance = distance_map.get(obj.pk)
        if distance is None:
            return None
        return round(distance, 2)

    def get_worker_location(self, obj: ServiceRequest) -> dict | None:
        """Get worker's current location if worker is assigned and has location."""
        if not obj.worker or not hasattr(obj.worker, 'worker_profile'):
            return None
        profile = obj.worker.worker_profile
        if profile.current_latitude is None or profile.current_longitude is None:
            return None
        return {
            "latitude": float(profile.current_latitude),
            "longitude": float(profile.current_longitude),
            "last_updated": profile.last_available_at.isoformat() if profile.last_available_at else None,
        }

    def get_worker_distance_km(self, obj: ServiceRequest) -> float | None:
        """Calculate distance from worker's current location to request location."""
        worker_location = self.get_worker_location(obj)
        if not worker_location:
            return None
        from .utils import haversine_km
        try:
            distance = haversine_km(
                worker_location["latitude"],
                worker_location["longitude"],
                float(obj.location_latitude),
                float(obj.location_longitude),
            )
            return round(distance, 2)
        except (ValueError, TypeError):
            return None


class ServiceRequestCreateSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.filter(is_active=True),
        source="category",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ServiceRequest
        fields = (
            "title",
            "description",
            "category_id",
            "priority",
            "location_latitude",
            "location_longitude",
            "address",
            "postcode",
            "scheduled_start",
            "customer_notes",
            "estimated_duration_minutes",
        )

    def create(self, validated_data: dict[str, Any]) -> ServiceRequest:
        request = self.context["request"]
        user: User = request.user
        validated_data["customer"] = user
        
        # Auto-fill address and postcode from coordinates if address is not provided or empty
        location_lat = validated_data.get("location_latitude")
        location_lng = validated_data.get("location_longitude")
        address = validated_data.get("address", "").strip()
        
        if (not address or address == "") and location_lat and location_lng:
            from .utils import reverse_geocode
            try:
                lat = float(location_lat)
                lng = float(location_lng)
                geocode_result = reverse_geocode(lat, lng)
                if geocode_result.get("address"):
                    validated_data["address"] = geocode_result["address"]
                if geocode_result.get("postcode"):
                    validated_data["postcode"] = geocode_result["postcode"]
            except (ValueError, TypeError):
                pass  # If geocoding fails, continue without address
        
        service_request = super().create(validated_data)
        RequestActivity.objects.create(
            service_request=service_request,
            actor=user,
            message=f"Request created with priority {service_request.priority}.",
        )
        notify_workers_of_request(service_request)
        return service_request


class ServiceRequestStatusSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)

    def _append_activity(self, request_obj: ServiceRequest, actor: User, message: str) -> None:
        note = self.validated_data.get("notes")
        if note:
            message = f"{message} Notes: {note}"
        RequestActivity.objects.create(
            service_request=request_obj,
            actor=actor,
            message=message,
        )

    def accept(self, request_obj: ServiceRequest, worker: User) -> ServiceRequest:
        with transaction.atomic():
            request_obj.assign_to_worker(worker)
            self._append_activity(
                request_obj,
                worker,
                f"Accepted by {worker.email}.",
            )
        return request_obj

    def start(self, request_obj: ServiceRequest, worker: User) -> ServiceRequest:
        request_obj.mark_in_progress()
        self._append_activity(
            request_obj,
            worker,
            f"Marked in progress by {worker.email}.",
        )
        return request_obj

    def complete(self, request_obj: ServiceRequest, worker: User) -> ServiceRequest:
        request_obj.mark_completed()
        notify_request_completed(request_obj)
        if request_obj.worker:
            WorkerProfile.objects.filter(user=request_obj.worker).update(
                total_completed_jobs=F("total_completed_jobs") + 1
            )
        self._append_activity(
            request_obj,
            worker,
            f"Completed by {worker.email}.",
        )
        return request_obj

    def cancel(self, request_obj: ServiceRequest, actor: User) -> ServiceRequest:
        request_obj.cancel(actor)
        notify_request_cancelled(request_obj, actor)
        self._append_activity(
            request_obj,
            actor,
            f"Cancelled by {actor.email}.",
        )
        return request_obj

