from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationMarkReadSerializer, NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == "true")
        return queryset


class NotificationMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = NotificationMarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = Notification.objects.filter(recipient=request.user)

        if data.get("read_all"):
            updated = queryset.mark_all_read()
        else:
            ids = data.get("notification_ids", [])
            updated = queryset.filter(id__in=ids).update(is_read=True, read_at=timezone.now())

        return Response({"updated": updated}, status=status.HTTP_200_OK)
