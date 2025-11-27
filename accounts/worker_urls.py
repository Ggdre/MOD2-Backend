from django.urls import path

from .views import WorkerStatusView

app_name = "worker"

urlpatterns = [
    path("status/", WorkerStatusView.as_view(), name="status"),
]

