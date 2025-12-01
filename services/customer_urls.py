from django.urls import path

from .views import SearchWorkersView, ServiceRequestViewSet

app_name = "customer"

urlpatterns = [
    path("requests/active/", ServiceRequestViewSet.as_view({"get": "my_active"}), name="active-requests"),
    path("requests/completed/", ServiceRequestViewSet.as_view({"get": "my_completed"}), name="completed-requests"),
    path("requests/pending/", ServiceRequestViewSet.as_view({"get": "my_pending"}), name="pending-requests"),
    path("workers/search/", SearchWorkersView.as_view(), name="search-workers"),
]

