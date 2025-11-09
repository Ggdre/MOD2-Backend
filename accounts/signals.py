from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomerProfile, User, WorkerProfile


@receiver(post_save, sender=User)
def ensure_profiles(sender, instance: User, created: bool, **kwargs):
    """Create or sync related profiles based on user role."""
    if instance.role == User.Role.WORKER:
        WorkerProfile.objects.get_or_create(user=instance)
    else:
        WorkerProfile.objects.filter(user=instance).delete()

    if instance.role == User.Role.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=instance)
    else:
        CustomerProfile.objects.filter(user=instance).delete()

