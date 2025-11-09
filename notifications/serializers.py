from __future__ import annotations

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "category",
            "event",
            "title",
            "body",
            "data",
            "reference_request",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class NotificationMarkReadSerializer(serializers.Serializer):
    read_all = serializers.BooleanField(default=False)
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, required=False
    )

    def validate(self, attrs):
        if not attrs.get("read_all") and not attrs.get("notification_ids"):
            raise serializers.ValidationError("Provide notification_ids or set read_all to true.")
        return attrs

