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

    def get(self, request, *args, **kwargs):
        """Get current user with worker profile & stats if user is a worker, or customer profile if customer."""
        user = self.get_object()
        serializer = self.get_serializer(user)
        data = serializer.data
        
        # Add worker stats if user is a worker
        if user.is_worker and hasattr(user, 'worker_profile'):
            from services.models import ServiceRequest
            from django.utils import timezone
            from datetime import timedelta
            
            profile = user.worker_profile
            
            # Get active jobs count
            active_jobs_count = ServiceRequest.objects.filter(
                worker=user,
                status__in=[ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS]
            ).count()
            
            # Get completed jobs today
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            completed_today = ServiceRequest.objects.filter(
                worker=user,
                status=ServiceRequest.Status.COMPLETED,
                completed_at__gte=today_start
            ).count()
            
            # Calculate earnings (sum of estimated amounts or you can add a price field later)
            # For now, we'll use a placeholder calculation or you can add a price field to ServiceRequest
            # This is a placeholder - you may want to add a price/amount field to ServiceRequest model
            completed_jobs_today_queryset = ServiceRequest.objects.filter(
                worker=user,
                status=ServiceRequest.Status.COMPLETED,
                completed_at__gte=today_start
            )
            # If you have a price field, use: earnings_today = sum(job.price for job in completed_jobs_today_queryset)
            # For now, using estimated_duration_minutes * rate (example: $10 per hour = $0.167 per minute)
            earnings_today = sum(
                (job.estimated_duration_minutes * 0.167) if job.estimated_duration_minutes else 0
                for job in completed_jobs_today_queryset
            )
            
            data['worker_stats'] = {
                'is_available': profile.is_available,
                'service_radius_km': profile.service_radius_km,
                'current_latitude': float(profile.current_latitude) if profile.current_latitude else None,
                'current_longitude': float(profile.current_longitude) if profile.current_longitude else None,
                'average_rating': float(profile.average_rating),
                'total_completed_jobs': profile.total_completed_jobs,
                'last_available_at': profile.last_available_at.isoformat() if profile.last_available_at else None,
                'active_jobs_count': active_jobs_count,
                'completed_today': completed_today,
                'earnings_today': round(earnings_today, 2),
            }
        
        # Add customer stats if user is a customer
        if user.is_customer and hasattr(user, 'customer_profile'):
            from services.models import ServiceRequest
            profile = user.customer_profile
            total_requests = ServiceRequest.objects.filter(customer=user).count()
            active_requests = ServiceRequest.objects.filter(
                customer=user,
                status__in=[ServiceRequest.Status.PENDING, ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS]
            ).count()
            completed_requests = ServiceRequest.objects.filter(
                customer=user,
                status=ServiceRequest.Status.COMPLETED
            ).count()
            
            data['customer_stats'] = {
                'total_requests': total_requests,
                'active_requests': active_requests,
                'completed_requests': completed_requests,
                'emergency_contact_name': profile.emergency_contact_name,
                'emergency_contact_phone': profile.emergency_contact_phone,
            }
        
        return Response(data)


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


class WorkerStatusView(APIView):
    """Update worker online/offline status with current location."""
    permission_classes = [permissions.IsAuthenticated, IsWorker]

    def patch(self, request):
        profile = getattr(request.user, "worker_profile", None)
        if profile is None:
            return Response({"detail": "Worker profile not found."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = WorkerAvailabilitySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.update(profile, serializer.validated_data)
        return Response(WorkerProfileSerializer(profile, context={"request": request}).data)


class LogoutView(APIView):
    """Logout endpoint that blacklists the refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                try:
                    token.blacklist()
                except AttributeError:
                    # If blacklist is not available, just return success
                    # The token will expire naturally
                    pass
                return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"detail": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {"detail": f"Error logging out: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )


class DeleteUserView(APIView):
    """Delete user account endpoint. Users can only delete their own account."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        """
        Delete the authenticated user's account.
        
        This will:
        - Delete the user and all related data (profiles, notifications, etc.)
        - Cascade delete service requests where user is the customer
        - Set worker to NULL on service requests where user is the worker
        - Delete declined jobs, notifications, and other related records
        """
        user = request.user
        
        # Check for active service requests as a customer
        from services.models import ServiceRequest
        active_customer_requests = ServiceRequest.objects.filter(
            customer=user,
            status__in=[
                ServiceRequest.Status.PENDING,
                ServiceRequest.Status.ACCEPTED,
                ServiceRequest.Status.IN_PROGRESS
            ]
        ).count()
        
        # Check for active service requests as a worker
        active_worker_requests = ServiceRequest.objects.filter(
            worker=user,
            status__in=[
                ServiceRequest.Status.ACCEPTED,
                ServiceRequest.Status.IN_PROGRESS
            ]
        ).count()
        
        # Store user email for response (before deletion)
        user_email = user.email
        
        # Delete the user (Django will handle cascading deletes)
        # Note: This will also delete:
        # - WorkerProfile/CustomerProfile (CASCADE)
        # - ServiceRequests where user is customer (CASCADE)
        # - Notifications (CASCADE)
        # - WorkerJobDecline records (CASCADE)
        # - ServiceRequests where user is worker will have worker set to NULL (SET_NULL)
        user.delete()
        
        return Response(
            {
                "detail": f"Account {user_email} has been successfully deleted.",
                "deleted_active_customer_requests": active_customer_requests,
                "deleted_active_worker_requests": active_worker_requests,
            },
            status=status.HTTP_200_OK
        )