from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Admin")
        WORKER = "WORKER", _("Worker")
        CUSTOMER = "CUSTOMER", _("Customer")

    username = None
    email = models.EmailField(_("email address"), unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )
    phone_number = models.CharField(max_length=32, blank=True)
    is_email_verified = models.BooleanField(default=False)
    default_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Default latitude for dispatching workers."),
    )
    default_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Default longitude for dispatching workers."),
    )
    default_address = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_worker(self) -> bool:
        return self.role == self.Role.WORKER

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER


class WorkerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile",
    )
    skills = models.TextField(blank=True)
    is_available = models.BooleanField(default=False)
    service_radius_km = models.PositiveIntegerField(
        default=20,
        validators=[MinValueValidator(1)],
        help_text=_("Maximum distance a worker is willing to travel (in km)."),
    )
    current_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    current_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    last_available_at = models.DateTimeField(null=True, blank=True)
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    total_completed_jobs = models.PositiveIntegerField(default=0)

    def set_available(self, available: bool, *, latitude: float | None = None, longitude: float | None = None) -> None:
        updates: list[str] = ["is_available"]
        self.is_available = available
        if available:
            self.last_available_at = timezone.now()
            updates.append("last_available_at")
            if latitude is not None:
                self.current_latitude = latitude
                updates.append("current_latitude")
            if longitude is not None:
                self.current_longitude = longitude
                updates.append("current_longitude")
        else:
            self.last_available_at = None
            updates.append("last_available_at")
        self.save(update_fields=updates)

    def __str__(self) -> str:
        return f"WorkerProfile<{self.user.email}>"


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"CustomerProfile<{self.user.email}>"
