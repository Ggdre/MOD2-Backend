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

        if self.action in {"retrieve"} and user.role == User.Role.WORKER:
            # Workers can view requests assigned to them or pending ones to evaluate
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

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsWorker])
    def accept(self, request, pk=None):
        service_request = ServiceRequest.objects.select_related("customer", "category").get(pk=pk)
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
