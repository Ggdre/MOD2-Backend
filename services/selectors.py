from __future__ import annotations

from typing import Dict, Iterable, Tuple

from accounts.models import User, WorkerProfile
from .models import ServiceRequest
from .utils import haversine_km


def get_worker_profile(worker: User) -> WorkerProfile | None:
    if worker.role != User.Role.WORKER:
        return None
    try:
        return worker.worker_profile
    except WorkerProfile.DoesNotExist:  # pragma: no cover - defensive
        return None


def get_pending_requests_for_worker(worker: User) -> Tuple[Iterable[ServiceRequest], Dict[int, float]]:
    profile = get_worker_profile(worker)
    if not profile or profile.current_latitude is None or profile.current_longitude is None:
        return ServiceRequest.objects.none(), {}

    worker_lat = float(profile.current_latitude)
    worker_lon = float(profile.current_longitude)
    max_distance = float(profile.service_radius_km)

    queryset = ServiceRequest.objects.filter(status=ServiceRequest.Status.PENDING)
    
    # Exclude jobs the worker has declined
    from .models import WorkerJobDecline
    declined_ids = WorkerJobDecline.objects.filter(worker=worker).values_list('service_request_id', flat=True)
    queryset = queryset.exclude(id__in=declined_ids)

    distance_map: dict[int, float] = {}
    filtered_ids: list[int] = []

    for request_obj in queryset:
        distance = haversine_km(
            worker_lat,
            worker_lon,
            float(request_obj.location_latitude),
            float(request_obj.location_longitude),
        )
        if distance <= max_distance:
            distance_map[request_obj.id] = distance
            filtered_ids.append(request_obj.id)

    if not filtered_ids:
        return ServiceRequest.objects.none(), {}

    filtered_queryset = ServiceRequest.objects.filter(id__in=filtered_ids).order_by("created_at")
    return filtered_queryset, distance_map

