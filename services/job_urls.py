from django.urls import path

from .views import (
    NearbyJobsView,
    ServiceRequestViewSet,
)

app_name = "jobs"

urlpatterns = [
    path("nearby/", NearbyJobsView.as_view(), name="nearby"),
    path("active/", ServiceRequestViewSet.as_view({"get": "active"}), name="active"),
    path("completed/", ServiceRequestViewSet.as_view({"get": "completed"}), name="completed"),
    path("<int:pk>/accept/", ServiceRequestViewSet.as_view({"post": "accept"}), name="accept"),
    path("<int:pk>/update-location/", ServiceRequestViewSet.as_view({"post": "update_location"}), name="update-location"),
]

