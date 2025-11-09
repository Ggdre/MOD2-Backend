from django.contrib import admin

from .models import RequestActivity, ServiceCategory, ServiceRequest


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reference_code",
        "title",
        "customer",
        "worker",
        "status",
        "priority",
        "created_at",
    )
    list_filter = ("status", "priority", "category")
    search_fields = ("reference_code", "title", "customer__email", "worker__email")
    raw_id_fields = ("customer", "worker")


@admin.register(RequestActivity)
class RequestActivityAdmin(admin.ModelAdmin):
    list_display = ("service_request", "actor", "message", "created_at")
    search_fields = ("service_request__reference_code", "actor__email", "message")
