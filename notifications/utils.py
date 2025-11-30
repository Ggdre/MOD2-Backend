from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from accounts.models import User, WorkerProfile
from services.models import ServiceRequest
from services.utils import haversine_km
from .models import Notification


@dataclass
class NotificationResult:
    notifications: List[Notification]

    @property
    def count(self) -> int:
        return len(self.notifications)


def create_notification(
    *,
    recipient: User,
    title: str,
    body: str = "",
    event: Notification.Event = Notification.Event.GENERIC,
    category: Notification.Category = Notification.Category.SYSTEM,
    reference_request: ServiceRequest | None = None,
    data: dict | None = None,
) -> Notification:
    notification, _ = Notification.objects.update_or_create(
        recipient=recipient,
        event=event,
        reference_request=reference_request,
        defaults={
            "title": title,
            "body": body,
            "category": category,
            "data": data or {},
            "is_read": False,
            "read_at": None,
        },
    )
    return notification


def _eligible_worker_profiles(service_request: ServiceRequest) -> Iterable[WorkerProfile]:
    """Get worker profiles eligible to receive notifications for a service request.
    
    Filters by:
    - is_available=True (only online workers)
    - Has location coordinates
    - Active user account
    - Worker category matches request category (if request has category)
    """
    queryset = WorkerProfile.objects.filter(
        is_available=True,  # Only online workers receive notifications
        current_latitude__isnull=False,
        current_longitude__isnull=False,
        user__is_active=True,
    )
    
    # Filter by category if the service request has a category
    if service_request.category:
        queryset = queryset.filter(category=service_request.category)
    
    return queryset.select_related("user")


def notify_workers_of_request(service_request: ServiceRequest) -> NotificationResult:
    """Notify nearby available workers about a new service request."""
    profiles = _eligible_worker_profiles(service_request)
    notifications: list[Notification] = []

    request_lat = float(service_request.location_latitude)
    request_lon = float(service_request.location_longitude)

    for profile in profiles:
        worker = profile.user
        distance = haversine_km(
            request_lat,
            request_lon,
            float(profile.current_latitude),
            float(profile.current_longitude),
        )
        if distance <= profile.service_radius_km:
            notification = Notification(
                recipient=worker,
                category=Notification.Category.REQUEST,
                event=Notification.Event.REQUEST_CREATED,
                title="New service request nearby",
                body=f"{service_request.title} requires attention.",
                data={
                    "request_id": service_request.id,
                    "reference_code": service_request.reference_code,
                    "distance_km": round(distance, 2),
                    "priority": service_request.priority,
                },
                reference_request=service_request,
            )
            notifications.append(notification)

    if notifications:
        Notification.objects.bulk_create(
            notifications,
            ignore_conflicts=True,
        )

    return NotificationResult(notifications=notifications)


def notify_request_accepted_by_worker(service_request: ServiceRequest, worker: User) -> Notification:
    title = f"Request {service_request.reference_code} accepted"
    body = f"{worker.first_name or worker.email} has accepted your request."
    return create_notification(
        recipient=service_request.customer,
        title=title,
        body=body,
        event=Notification.Event.REQUEST_ACCEPTED,
        category=Notification.Category.REQUEST,
        reference_request=service_request,
        data={
            "worker_id": worker.id,
            "worker_email": worker.email,
            "request_id": service_request.id,
        },
    )


def notify_request_completed(service_request: ServiceRequest) -> Notification:
    worker = service_request.worker
    worker_email = worker.email if worker else ""
    title = f"Request {service_request.reference_code} completed"
    body = "Your maintenance request has been marked as completed."
    return create_notification(
        recipient=service_request.customer,
        title=title,
        body=body,
        event=Notification.Event.REQUEST_COMPLETED,
        category=Notification.Category.WORKFLOW,
        reference_request=service_request,
        data={
            "request_id": service_request.id,
            "worker_email": worker_email,
        },
    )


def notify_request_cancelled(service_request: ServiceRequest, actor: User) -> NotificationResult:
    recipients: list[User] = []
    if service_request.customer != actor:
        recipients.append(service_request.customer)
    if service_request.worker and service_request.worker != actor:
        recipients.append(service_request.worker)

    notifications: list[Notification] = []
    for recipient in recipients:
        notifications.append(
            create_notification(
                recipient=recipient,
                title=f"Request {service_request.reference_code} cancelled",
                body=f"The request was cancelled by {actor.email}.",
                event=Notification.Event.REQUEST_CANCELLED,
                category=Notification.Category.REQUEST,
                reference_request=service_request,
                data={"request_id": service_request.id, "cancelled_by": actor.email},
            )
        )
    return NotificationResult(notifications=notifications)

