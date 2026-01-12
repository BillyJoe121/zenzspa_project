from rest_framework import serializers


class TOTPSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)


class TOTPVerifySerializer(serializers.Serializer):
    token = serializers.CharField(max_length=6, min_length=6)
