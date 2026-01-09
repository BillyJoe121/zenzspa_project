"""
Vistas administrativas para exportación de usuarios.
"""
import csv

from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from ..models import CustomUser
from ..serializers import UserExportSerializer
from ..throttling import AdminRateThrottle


class UserExportView(generics.GenericAPIView):
    """Exporta usuarios en formato JSON o CSV."""

    permission_classes = [IsAdminUser]
    throttle_classes = [AdminRateThrottle]
    queryset = CustomUser.objects.all()
    serializer_class = UserExportSerializer

    def get(self, request, *args, **kwargs):
        format_param = request.query_params.get('format', None)

        if format_param == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="users_export.csv"'

            writer = csv.writer(response)
            writer.writerow(['ID', 'Phone', 'Email', 'First Name', 'Last Name', 'Role', 'Status', 'Created At'])

            for user in self.get_queryset():
                status_label = "Active" if user.is_active else "Inactive"
                if user.is_persona_non_grata:
                    status_label = "CNG"
                writer.writerow([
                    user.id, user.phone_number, user.email, user.first_name, user.last_name,
                    user.role, status_label, user.created_at
                ])
            return response

        # Return JSON for non-CSV requests
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
