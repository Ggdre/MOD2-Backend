from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(is_read=False)

    def mark_all_read(self):
        return self.update(is_read=True, read_at=timezone.now())


class Notification(models.Model):
    class Category(models.TextChoices):
        REQUEST = "REQUEST", _("Request")
        SYSTEM = "SYSTEM", _("System")
        WORKFLOW = "WORKFLOW", _("Workflow")

    class Event(models.TextChoices):
        REQUEST_CREATED = "REQUEST_CREATED", _("Request created")
        REQUEST_ACCEPTED = "REQUEST_ACCEPTED", _("Request accepted")
        REQUEST_COMPLETED = "REQUEST_COMPLETED", _("Request completed")
        REQUEST_CANCELLED = "REQUEST_CANCELLED", _("Request cancelled")
        GENERIC = "GENERIC", _("Generic message")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notifications",
        on_delete=models.CASCADE,
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    event = models.CharField(max_length=40, choices=Event.choices, default=Event.GENERIC)
    title = models.CharField(max_length=140)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    reference_request = models.ForeignKey(
        "services.ServiceRequest",
        related_name="notifications",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "event", "reference_request"),
                name="unique_notification_per_event",
            )
        ]

    def mark_read(self, *, commit: bool = True) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            if commit:
                self.save(update_fields=["is_read", "read_at"])

    def __str__(self) -> str:
        return f"Notification<{self.category}:{self.event} -> {self.recipient.email}>"
