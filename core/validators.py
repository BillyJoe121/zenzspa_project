from rest_framework import serializers

def percentage_0_100(value: int):
    if value < 0 or value > 100:
        raise serializers.ValidationError("Debe estar entre 0 y 100.")
