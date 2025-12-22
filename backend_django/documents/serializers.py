from rest_framework import serializers
from .models import Document, Asset


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["id", "type", "page", "storage_key", "meta", "created_at"]
        read_only_fields = ["id", "created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "original_filename",
            "storage_key_original",
            "status",
            "meta",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DocumentDetailSerializer(serializers.ModelSerializer):
    assets = AssetSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "original_filename",
            "storage_key_original",
            "status",
            "meta",
            "created_at",
            "updated_at",
            "assets",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "assets"]

class DocumentIngestRequestSerializer(serializers.Serializer):
    file = serializers.FileField()