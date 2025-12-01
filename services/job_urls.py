from django.urls import path

from .views import (
    NearbyJobsView,
    ServiceCategoryViewSet,
    ServiceRequestViewSet,
)

app_name = "jobs"

urlpatterns = [
    path("nearby/", NearbyJobsView.as_view(), name="nearby"),
    path("categories/", ServiceCategoryViewSet.as_view({"get": "list"}), name="categories"),
    path("active/", ServiceRequestViewSet.as_view({"get": "active"}), name="active"),
    path("completed/", ServiceRequestViewSet.as_view({"get": "completed"}), name="completed"),
    path("declined/", ServiceRequestViewSet.as_view({"get": "declined"}), name="declined"),
    path("<int:pk>/accept/", ServiceRequestViewSet.as_view({"post": "accept"}), name="accept"),
    path("<int:pk>/decline/", ServiceRequestViewSet.as_view({"post": "decline"}), name="decline"),
    path("<int:pk>/update-location/", ServiceRequestViewSet.as_view({"post": "update_location"}), name="update-location"),
]

