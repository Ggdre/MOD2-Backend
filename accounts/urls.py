from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CurrentUserView,
    GoogleAuthView,
    LoginView,
    LogoutView,
    RegisterView,
    WorkerAvailabilityView,
    WorkerStatusView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("workers/availability/", WorkerAvailabilityView.as_view(), name="worker-availability"),
    path("google/", GoogleAuthView.as_view(), name="google-login"),
]

