from rest_framework import serializers

class ChatTurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()

class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField()
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=50)
    doc_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
    )
    history = ChatTurnSerializer(many=True, required=False, allow_null=True)

    # Persistencia
    conversation_id = serializers.UUIDField(required=False, allow_null=True)

class AskResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    context = serializers.ListField(child=serializers.DictField())
    table_path = serializers.CharField(required=False, allow_null=True)
    image_path = serializers.CharField(required=False, allow_null=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)

class QueryRequestSerializer(serializers.Serializer):
    query = serializers.CharField()
    top_k = serializers.IntegerField(required=False, default=5, min_value=1, max_value=50)
