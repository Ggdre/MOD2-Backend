from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsWorker
from .serializers import (
    AuthTokenSerializer,
    GoogleAuthSerializer,
    RegisterSerializer,
    UserSerializer,
    WorkerAvailabilitySerializer,
    WorkerProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class LoginView(TokenObtainPairView):
    serializer_class = AuthTokenSerializer
    permission_classes = [permissions.AllowAny]


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class WorkerAvailabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsWorker]

    def get(self, request):
        profile = getattr(request.user, "worker_profile", None)
        if profile is None:
            return Response({"detail": "Worker profile not found."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WorkerProfileSerializer(profile, context={"request": request}).data)

    def patch(self, request):
        profile = getattr(request.user, "worker_profile", None)
        if profile is None:
            return Response({"detail": "Worker profile not found."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = WorkerAvailabilitySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.update(profile, serializer.validated_data)
        return Response(WorkerProfileSerializer(profile, context={"request": request}).data)


class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data, status=status.HTTP_200_OK if not data.get("created") else status.HTTP_201_CREATED)
