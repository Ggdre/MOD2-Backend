from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DashboardMetricsView, ServiceCategoryViewSet, ServiceRequestViewSet

app_name = "services"

router = DefaultRouter()
router.register("requests", ServiceRequestViewSet, basename="service-request")
router.register("categories", ServiceCategoryViewSet, basename="service-category")

urlpatterns = [
    path("dashboard/", DashboardMetricsView.as_view(), name="dashboard-metrics"),
    path("", include(router.urls)),
]

