from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "event", "category", "is_read", "created_at")
    list_filter = ("category", "event", "is_read")
    search_fields = ("recipient__email", "title", "body")
