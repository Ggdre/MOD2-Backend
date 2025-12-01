from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdminUserRole, IsCustomer, IsWorker
from accounts.serializers import UserSerializer
from notifications.utils import notify_request_accepted_by_worker
from .models import ServiceCategory, ServiceRequest
from .selectors import get_pending_requests_for_worker
from .serializers import (
    ServiceCategorySerializer,
    ServiceRequestCreateSerializer,
    ServiceRequestSerializer,
    ServiceRequestStatusSerializer,
)


class ServiceCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ServiceCategory.objects.filter(is_active=True)
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.AllowAny]


class ServiceRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ServiceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ServiceRequest.objects.select_related("customer", "worker", "category").prefetch_related(
            "activities__actor"
        )
        user: User = self.request.user

        if self.action in {"retrieve", "accept", "decline"} and user.role == User.Role.WORKER:
            # Workers can view/accept/decline requests assigned to them or pending ones to evaluate
            return queryset.filter(Q(worker=user) | Q(status=ServiceRequest.Status.PENDING))

        if user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.CUSTOMER:
            return queryset.filter(customer=user)
        if user.role == User.Role.WORKER:
            return queryset.filter(worker=user)
        return queryset.none()

    def get_serializer_class(self):
        if self.action == "create":
            return ServiceRequestCreateSerializer
        return super().get_serializer_class()

    def filter_queryset(self, queryset):
        status_param = self.request.query_params.get("status")
        priority_param = self.request.query_params.get("priority")
        if status_param:
            queryset = queryset.filter(status=status_param)
        if priority_param:
            queryset = queryset.filter(priority=priority_param)
        return queryset

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.CUSTOMER:
            return Response({"detail": "Only customers can create service requests."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def pending(self, request):
        queryset, distance_map = get_pending_requests_for_worker(request.user)
        page = self.paginate_queryset(queryset)
        target_objects = list(page) if page is not None else list(queryset)
        context = {
            "request": request,
            "distance_map": {obj.id: distance_map.get(obj.id) for obj in target_objects},
        }
        serializer = ServiceRequestSerializer(target_objects, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def active(self, request):
        queryset = ServiceRequest.objects.filter(
            worker=request.user,
            status__in=[ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS],
        ).select_related("customer", "category")
        serializer = ServiceRequestSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def completed(self, request):
        """Get completed jobs for the worker."""
        queryset = ServiceRequest.objects.filter(
            worker=request.user,
            status=ServiceRequest.Status.COMPLETED,
        ).select_related("customer", "category").order_by("-completed_at")
        serializer = ServiceRequestSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsCustomer])
    def my_active(self, request):
        """Get active requests for the customer."""
        queryset = ServiceRequest.objects.filter(
            customer=request.user,
            status__in=[ServiceRequest.Status.PENDING, ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS],
        ).select_related("worker", "category").order_by("-created_at")
        serializer = ServiceRequestSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsCustomer])
    def my_completed(self, request):
        """Get completed requests for the customer."""
        queryset = ServiceRequest.objects.filter(
            customer=request.user,
            status=ServiceRequest.Status.COMPLETED,
        ).select_related("worker", "category").order_by("-completed_at")
        serializer = ServiceRequestSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsCustomer])
    def my_pending(self, request):
        """Get pending requests for the customer."""
        queryset = ServiceRequest.objects.filter(
            customer=request.user,
            status=ServiceRequest.Status.PENDING,
        ).select_related("category").order_by("-created_at")
        serializer = ServiceRequestSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def accept(self, request, pk=None):
        service_request = self.get_object()
        if service_request.status != ServiceRequest.Status.PENDING:
            return Response({"detail": "Request is no longer available."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ServiceRequestStatusSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.accept(service_request, request.user)
            notify_request_accepted_by_worker(service_request, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_serializer = ServiceRequestSerializer(service_request, context={"request": request})
        return Response(response_serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def start(self, request, pk=None):
        service_request = self.get_object()
        if service_request.worker != request.user:
            return Response({"detail": "You are not assigned to this request."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ServiceRequestStatusSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.start(service_request, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_serializer = ServiceRequestSerializer(service_request, context={"request": request})
        return Response(response_serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def update_location(self, request, pk=None):
        """Update worker's location and status (on the way, arrived) for an accepted job."""
        service_request = self.get_object()
        if service_request.worker != request.user:
            return Response({"detail": "You are not assigned to this request."}, status=status.HTTP_403_FORBIDDEN)
        
        if service_request.status not in [ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS]:
            return Response(
                {"detail": "Location can only be updated for accepted or in-progress requests."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        status_update = request.data.get("status")  # "on_the_way" or "arrived"
        
        if not latitude or not longitude:
            return Response(
                {"detail": "Latitude and longitude are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (ValueError, TypeError):
            return Response(
                {"detail": "Invalid latitude or longitude values."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update worker profile location
        profile = getattr(request.user, "worker_profile", None)
        if profile:
            profile.current_latitude = latitude
            profile.current_longitude = longitude
            profile.last_available_at = timezone.now()
            profile.save(update_fields=["current_latitude", "current_longitude", "last_available_at"])
        
        # Update request status if worker has arrived
        if status_update == "arrived" and service_request.status == ServiceRequest.Status.ACCEPTED:
            service_request.mark_in_progress()
            from .models import RequestActivity
            RequestActivity.objects.create(
                service_request=service_request,
                actor=request.user,
                message=f"Worker {request.user.email} has arrived at the location.",
            )
        
        # Create activity log
        from .models import RequestActivity
        status_message = "arrived at location" if status_update == "arrived" else "is on the way"
        RequestActivity.objects.create(
            service_request=service_request,
            actor=request.user,
            message=f"Worker {request.user.email} {status_message}. Location updated.",
        )
        
        response_serializer = ServiceRequestSerializer(service_request, context={"request": request})
        return Response(response_serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def track_worker(self, request, pk=None):
        """Get worker location and tracking info for a customer's request."""
        service_request = self.get_object()
        
        # Only customer or assigned worker can track
        if request.user.role == User.Role.CUSTOMER and service_request.customer != request.user:
            return Response({"detail": "You can only track your own requests."}, status=status.HTTP_403_FORBIDDEN)
        
        if not service_request.worker:
            return Response(
                {"detail": "No worker assigned to this request yet."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        profile = getattr(service_request.worker, "worker_profile", None)
        if not profile or profile.current_latitude is None or profile.current_longitude is None:
            return Response(
                {
                    "worker": UserSerializer(service_request.worker, context={"request": request}).data,
                    "location": None,
                    "distance_km": None,
                    "status": service_request.status,
                }
            )
        
        from .utils import haversine_km
        distance = haversine_km(
            float(profile.current_latitude),
            float(profile.current_longitude),
            float(service_request.location_latitude),
            float(service_request.location_longitude),
        )
        
        return Response({
            "worker": UserSerializer(service_request.worker, context={"request": request}).data,
            "location": {
                "latitude": float(profile.current_latitude),
                "longitude": float(profile.current_longitude),
                "last_updated": profile.last_available_at.isoformat() if profile.last_available_at else None,
            },
            "distance_km": round(distance, 2),
            "status": service_request.status,
            "request_location": {
                "latitude": float(service_request.location_latitude),
                "longitude": float(service_request.location_longitude),
                "address": service_request.address,
            },
        })

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def complete(self, request, pk=None):
        service_request = self.get_object()
        if service_request.worker != request.user:
            return Response({"detail": "You are not assigned to this request."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ServiceRequestStatusSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.complete(service_request, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_serializer = ServiceRequestSerializer(service_request, context={"request": request})
        return Response(response_serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def cancel(self, request, pk=None):
        service_request = self.get_object()
        user = request.user
        can_cancel = (
            user.role == User.Role.ADMIN
            or service_request.customer == user
            or (service_request.worker == user and service_request.status != ServiceRequest.Status.COMPLETED)
        )
        if not can_cancel:
            return Response({"detail": "You are not allowed to cancel this request."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ServiceRequestStatusSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.cancel(service_request, user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_serializer = ServiceRequestSerializer(service_request, context={"request": request})
        return Response(response_serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def decline(self, request, pk=None):
        """Worker declines/expresses not interested in a job."""
        service_request = self.get_object()
        
        if service_request.status != ServiceRequest.Status.PENDING:
            return Response(
                {"detail": "Only pending requests can be declined."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .models import WorkerJobDecline
        reason = request.data.get("reason", "")
        
        # Create or get existing decline record
        decline, created = WorkerJobDecline.objects.get_or_create(
            worker=request.user,
            service_request=service_request,
            defaults={"reason": reason}
        )
        
        if not created:
            # Update reason if already declined
            decline.reason = reason
            decline.save(update_fields=["reason"])
        
        # Create activity log
        from .models import RequestActivity
        RequestActivity.objects.create(
            service_request=service_request,
            actor=request.user,
            message=f"Declined by {request.user.email}. Reason: {reason if reason else 'Not interested'}",
        )
        
        return Response({
            "detail": "Job declined. This job will no longer appear in your search results.",
            "message": "Cancelled for you"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def declined(self, request):
        """Get all jobs that the worker has declined."""
        from .models import WorkerJobDecline
        
        declined_records = WorkerJobDecline.objects.filter(
            worker=request.user
        ).select_related("service_request__customer", "service_request__category", "service_request__worker")
        
        declined_jobs = [record.service_request for record in declined_records]
        
        serializer = ServiceRequestSerializer(declined_jobs, many=True, context={"request": request})
        
        # Add decline reason and date to each job
        result_data = serializer.data
        for i, record in enumerate(declined_records):
            result_data[i]["decline_reason"] = record.reason
            result_data[i]["declined_at"] = record.created_at.isoformat()
        
        return Response(result_data)


class NearbyJobsView(APIView):
    """Get nearby jobs within worker's service radius, filtered by worker's category/specialization and location."""
    permission_classes = [permissions.IsAuthenticated, IsWorker]

    def get(self, request):
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        category_id = request.query_params.get("category_id")
        max_distance_km = request.query_params.get("max_distance_km")
        
        # Location is required
        if not lat or not lng:
            return Response(
                {"detail": "Both 'lat' and 'lng' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            worker_lat = float(lat)
            worker_lng = float(lng)
        except ValueError:
            return Response(
                {"detail": "Invalid latitude or longitude values."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        profile = getattr(request.user, "worker_profile", None)
        if profile is None:
            return Response(
                {"detail": "Worker profile not found."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use provided max_distance or worker's service radius
        if max_distance_km:
            try:
                max_distance = float(max_distance_km)
            except ValueError:
                return Response(
                    {"detail": "Invalid max_distance_km value."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            max_distance = float(profile.service_radius_km)
        
        # Start with pending jobs
        queryset = ServiceRequest.objects.filter(status=ServiceRequest.Status.PENDING)
        
        # Filter by category if provided, otherwise use worker's category
        if category_id:
            try:
                category_id = int(category_id)
                queryset = queryset.filter(category_id=category_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid category_id."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif profile.category:
            queryset = queryset.filter(category=profile.category)
        
        # Exclude jobs the worker has declined
        from .models import WorkerJobDecline
        declined_ids = WorkerJobDecline.objects.filter(worker=request.user).values_list('service_request_id', flat=True)
        queryset = queryset.exclude(id__in=declined_ids)
        
        distance_map: dict[int, float] = {}
        filtered_ids: list[int] = []
        
        from .utils import haversine_km
        
        for request_obj in queryset:
            distance = haversine_km(
                worker_lat,
                worker_lng,
                float(request_obj.location_latitude),
                float(request_obj.location_longitude),
            )
            if distance <= max_distance:
                distance_map[request_obj.id] = distance
                filtered_ids.append(request_obj.id)
        
        if not filtered_ids:
            return Response([])
        
        filtered_queryset = ServiceRequest.objects.filter(
            id__in=filtered_ids
        ).select_related("customer", "category").order_by("created_at")
        
        context = {
            "request": request,
            "distance_map": distance_map,
        }
        serializer = ServiceRequestSerializer(filtered_queryset, many=True, context=context)
        return Response(serializer.data)


class SearchWorkersView(APIView):
    """Search for workers with filtering by rating, category, and location. Only shows active worker profiles."""
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get(self, request):
        from accounts.models import WorkerProfile
        from accounts.serializers import WorkerProfileSerializer
        
        # Get query parameters
        category_id = request.query_params.get("category_id")
        min_rating = request.query_params.get("min_rating")
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        max_distance_km = request.query_params.get("max_distance_km")
        
        # Start with active worker profiles only (using user.is_active)
        queryset = WorkerProfile.objects.filter(
            user__is_active=True,
        ).select_related("user", "category")
        
        # Filter by category if provided
        if category_id:
            try:
                category_id = int(category_id)
                queryset = queryset.filter(category_id=category_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid category_id."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Filter by minimum rating if provided
        if min_rating:
            try:
                min_rating = float(min_rating)
                if min_rating < 0 or min_rating > 5:
                    return Response(
                        {"detail": "min_rating must be between 0 and 5."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                queryset = queryset.filter(average_rating__gte=min_rating)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid min_rating value."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Filter by location if provided
        if lat and lng:
            try:
                search_lat = float(lat)
                search_lng = float(lng)
                max_distance = float(max_distance_km) if max_distance_km else 50.0  # Default 50km
                
                from .utils import haversine_km
                
                # Filter workers within distance
                filtered_profiles = []
                for profile in queryset:
                    if profile.current_latitude and profile.current_longitude:
                        distance = haversine_km(
                            search_lat,
                            search_lng,
                            float(profile.current_latitude),
                            float(profile.current_longitude),
                        )
                        if distance <= max_distance:
                            # Add distance to profile for sorting
                            profile.distance_km = distance
                            filtered_profiles.append(profile)
                
                # Sort by distance
                filtered_profiles.sort(key=lambda p: getattr(p, 'distance_km', float('inf')))
                
                # Serialize with distance
                serializer = WorkerProfileSerializer(filtered_profiles, many=True, context={"request": request})
                data = serializer.data
                
                # Add distance to each result
                for i, profile in enumerate(filtered_profiles):
                    if hasattr(profile, 'distance_km'):
                        data[i]['distance_km'] = round(profile.distance_km, 2)
                
                return Response(data)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid latitude or longitude values."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # If no location filter, just return all matching workers
        # Order by rating and completed jobs
        queryset = queryset.order_by("-average_rating", "-total_completed_jobs")
        
        serializer = WorkerProfileSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)


class DashboardMetricsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        now = timezone.now()
        open_requests = ServiceRequest.objects.filter(
            status__in=[ServiceRequest.Status.PENDING, ServiceRequest.Status.ACCEPTED, ServiceRequest.Status.IN_PROGRESS]
        )
        data = {
            "totals": {
                "customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
                "workers": User.objects.filter(role=User.Role.WORKER).count(),
                "open_requests": open_requests.count(),
                "emergencies": open_requests.filter(priority=ServiceRequest.Priority.EMERGENCY).count(),
            },
            "requests_by_status": ServiceRequest.objects.values("status").annotate(count=Count("id")),
            "recent_requests": ServiceRequestSerializer(
                ServiceRequest.objects.order_by("-created_at")[:10],
                many=True,
                context={"request": request},
            ).data,
            "top_workers": UserSerializer(
                User.objects.filter(role=User.Role.WORKER, worker_profile__isnull=False)
                .order_by("-worker_profile__total_completed_jobs")[:5],
                many=True,
                context={"request": request},
            ).data,
            "generated_at": now,
        }
        return Response(data)
