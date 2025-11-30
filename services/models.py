from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ServiceCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ServiceRequestQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status__in=[ServiceRequest.Status.COMPLETED, ServiceRequest.Status.CANCELLED])

    def emergencies(self):
        return self.filter(priority=ServiceRequest.Priority.EMERGENCY)

    def for_worker(self, worker):
        return self.filter(worker=worker)


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        ACCEPTED = "ACCEPTED", _("Accepted")
        IN_PROGRESS = "IN_PROGRESS", _("In progress")
        COMPLETED = "COMPLETED", _("Completed")
        CANCELLED = "CANCELLED", _("Cancelled")

    class Priority(models.TextChoices):
        STANDARD = "STANDARD", _("Standard")
        EMERGENCY = "EMERGENCY", _("Emergency")

    reference_code = models.CharField(max_length=12, unique=True, editable=False)
    title = models.CharField(max_length=140)
    description = models.TextField()
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="service_requests",
        on_delete=models.CASCADE,
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="accepted_requests",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    category = models.ForeignKey(
        ServiceCategory,
        related_name="service_requests",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.STANDARD,
    )
    location_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.CharField(max_length=255, blank=True)
    postcode = models.CharField(max_length=20, blank=True, help_text=_("Postal code extracted from address"))
    scheduled_start = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    customer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(default=60)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ServiceRequestQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status",)),
            models.Index(fields=("priority", "status")),
            models.Index(fields=("customer",)),
            models.Index(fields=("worker",)),
        ]

    def __str__(self) -> str:
        return f"{self.reference_code} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            self.reference_code = uuid.uuid4().hex[:12].upper()
        super().save(*args, **kwargs)

    @property
    def is_open(self) -> bool:
        return self.status in {self.Status.PENDING, self.Status.ACCEPTED, self.Status.IN_PROGRESS}

    def assign_to_worker(self, worker) -> None:
        if self.status not in {self.Status.PENDING, self.Status.ACCEPTED}:
            raise ValueError(_("Request cannot be reassigned in its current status."))
        with transaction.atomic():
            refreshed = ServiceRequest.objects.select_for_update().get(pk=self.pk)
            if refreshed.status != ServiceRequest.Status.PENDING:
                raise ValueError(_("Request is no longer available."))
            refreshed.worker = worker
            refreshed.status = ServiceRequest.Status.ACCEPTED
            refreshed.accepted_at = timezone.now()
            refreshed.save(update_fields=["worker", "status", "accepted_at", "updated_at"])
            self.refresh_from_db()

    def mark_in_progress(self):
        if self.status != self.Status.ACCEPTED:
            raise ValueError(_("Only accepted requests can start."))
        self.status = self.Status.IN_PROGRESS
        self.save(update_fields=["status", "updated_at"])

    def mark_completed(self):
        if self.status not in {self.Status.ACCEPTED, self.Status.IN_PROGRESS}:
            raise ValueError(_("Only active requests can be completed."))
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def cancel(self, by_user):
        if self.status == self.Status.COMPLETED:
            raise ValueError(_("Completed requests cannot be cancelled."))
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.admin_notes = f"{self.admin_notes}\nCancelled by {by_user.email} at {self.cancelled_at:%Y-%m-%d %H:%M:%S}"[:1000]
        self.save(update_fields=["status", "cancelled_at", "updated_at", "admin_notes"])


class RequestActivity(models.Model):
    service_request = models.ForeignKey(ServiceRequest, related_name="activities", on_delete=models.CASCADE)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="request_activities",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.service_request.reference_code}: {self.message[:50]}"
