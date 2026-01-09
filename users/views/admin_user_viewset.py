"""
ViewSet administrativo para CRUD de usuarios.
"""
from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework.decorators import action

from core.models import AuditLog
from ..models import CustomUser, UserSession
from ..serializers import AdminUserSerializer
from ..throttling import AdminRateThrottle


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    CRUD administrativo para usuarios.

    Reglas de permisos:
    - SuperAdmin (is_superuser=True): Puede ver y gestionar TODOS los usuarios, incluyendo otros admins.
    - Admin (role=ADMIN, is_superuser=False): Solo puede ver y gestionar clientes, VIPs y staff.
      NO puede ver ni modificar superadmins ni otros admins.
    """

    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    throttle_classes = [AdminRateThrottle]

    def get_queryset(self):
        """
        Retorna el queryset de usuarios con filtros opcionales.

        IMPORTANTE: Los admins regulares NO ven superadmins ni otros admins.
        Solo superadmins ven a todos los usuarios.

        Query params:
        - search: busca por nombre, apellido, email o teléfono
        - role: filtra por rol (CLIENT, VIP, STAFF, ADMIN)
        - is_active: filtra por estado activo (true/false)
        """
        queryset = CustomUser.objects.select_related('profile').order_by('-created_at')

        # PROTECCIÓN: Admins regulares no ven superadmins ni otros admins
        user = self.request.user
        if not user.is_superuser:
            # Excluir superadmins y otros admins del queryset
            queryset = queryset.exclude(is_superuser=True)
            queryset = queryset.exclude(role=CustomUser.Role.ADMIN)

        # Filtro de búsqueda
        search = self.request.query_params.get('search', None)
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        # Filtro por rol
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)

        # Filtro por estado activo
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_active=is_active_bool)

        return queryset

    def check_object_permissions(self, request, obj):
        """
        Verificaciones adicionales de permisos a nivel de objeto.
        """
        super().check_object_permissions(request, obj)

        user = request.user

        # PROTECCIÓN: Solo superadmins pueden acceder a superadmins
        if obj.is_superuser and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permisos para acceder a este usuario.")

        # PROTECCIÓN: Solo superadmins pueden acceder a otros admins
        if obj.role == CustomUser.Role.ADMIN and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permisos para gestionar administradores.")

    def perform_create(self, serializer):
        """
        Valida permisos antes de crear usuarios.
        Solo superadmins pueden crear usuarios con rol ADMIN.
        """
        user = self.request.user
        new_role = serializer.validated_data.get('role', CustomUser.Role.CLIENT)

        if new_role == CustomUser.Role.ADMIN and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo los superadministradores pueden crear administradores.")

        serializer.save()

    def perform_update(self, serializer):
        """
        Valida permisos antes de actualizar usuarios.
        - Solo superadmins pueden modificar admins o superadmins.
        - Solo superadmins pueden cambiar rol a ADMIN.
        """
        user = self.request.user
        instance = self.get_object()
        new_role = serializer.validated_data.get('role', instance.role)

        # Verificar si está intentando modificar un admin/superadmin
        if (instance.role == CustomUser.Role.ADMIN or instance.is_superuser) and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo los superadministradores pueden modificar administradores.")

        # Verificar si está intentando promover a admin
        if new_role == CustomUser.Role.ADMIN and instance.role != CustomUser.Role.ADMIN and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo los superadministradores pueden promover usuarios a administrador.")

        serializer.save()

    def perform_destroy(self, instance):
        """
        Soft delete con validación de permisos.
        Solo superadmins pueden eliminar admins.
        """
        user = self.request.user

        # PROTECCIÓN: Solo superadmins pueden eliminar admins o superadmins
        if (instance.role == CustomUser.Role.ADMIN or instance.is_superuser) and not user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo los superadministradores pueden eliminar administradores.")

        # PROTECCIÓN: Un superadmin no puede eliminarse a sí mismo
        if instance.id == user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No puedes eliminar tu propia cuenta.")

        # Soft delete para no romper integridad de datos
        instance.is_active = False
        instance.is_persona_non_grata = True
        instance.save(update_fields=['is_active', 'is_persona_non_grata', 'updated_at'])
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=instance,
            action=AuditLog.Action.FLAG_NON_GRATA,
            details="Usuario desactivado desde API admin.",
        )

    @action(detail=True, methods=['delete'], url_path='permanent')
    def permanent_delete(self, request, pk=None):
        """
        Elimina PERMANENTEMENTE un usuario de la base de datos.

        SOLO DISPONIBLE PARA SUPERADMINS.
        Esta acción es IRREVERSIBLE.

        Restricciones:
        - Solo superadmins pueden usar este endpoint
        - No se puede eliminar a sí mismo
        - No se puede eliminar a otro superadmin

        DELETE /api/v1/auth/admin/users/{id}/permanent/
        """
        from rest_framework.exceptions import PermissionDenied

        user = request.user

        # Solo superadmins pueden usar este endpoint
        if not user.is_superuser:
            raise PermissionDenied("Solo los superadministradores pueden eliminar usuarios permanentemente.")

        instance = self.get_object()

        # No se puede eliminar a sí mismo
        if instance.id == user.id:
            raise PermissionDenied("No puedes eliminar tu propia cuenta.")

        # No se puede eliminar a otro superadmin
        if instance.is_superuser:
            raise PermissionDenied("No puedes eliminar a otro superadministrador.")

        # Guardar datos para el log antes de eliminar
        user_data = {
            "id": str(instance.id),
            "phone_number": instance.phone_number,
            "email": instance.email,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "role": instance.role,
        }

        # Registrar en AuditLog ANTES de eliminar (porque después el target_user no existirá)
        AuditLog.objects.create(
            admin_user=user,
            target_user=None,  # El usuario será eliminado
            action=AuditLog.Action.USER_DELETED_PERMANENTLY,
            details=f"Usuario eliminado permanentemente: {user_data}",
        )

        # Eliminar sesiones y tokens del usuario
        UserSession.objects.filter(user=instance).delete()
        OutstandingToken.objects.filter(user=instance).delete()

        # Eliminar perfil clínico si existe (y sus datos relacionados)
        if hasattr(instance, 'profile') and instance.profile:
            instance.profile.delete()

        # Eliminar el usuario permanentemente
        instance.delete()

        return Response(
            {"detail": f"Usuario '{user_data['first_name']} {user_data['last_name']}' eliminado permanentemente."},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='search-by-phone')
    def search_by_phone(self, request):
        """
        DEPRECATED: Usar search-clients en su lugar.
        Busca clientes por número de teléfono para creación de citas por admin.

        GET /api/v1/auth/admin/users/search-by-phone/?phone=+573...

        Returns:
            Lista de hasta 10 usuarios que coinciden con el teléfono.
            Excluye usuarios marcados como Persona Non Grata.
        """
        from django.db.models import Q

        phone = request.query_params.get('phone', '').strip()
        if not phone or len(phone) < 4:
            return Response(
                {'error': 'Se requiere un número de teléfono con al menos 4 dígitos.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Buscar clientes y VIPs que coincidan con el teléfono
        users = CustomUser.objects.filter(
            Q(phone_number__icontains=phone),
            role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
            is_persona_non_grata=False,
            is_active=True,
        ).select_related('profile')[:10]

        # Usar SimpleUserSerializer para la respuesta
        from ..serializers import SimpleUserSerializer
        return Response(SimpleUserSerializer(users, many=True).data)

    @action(detail=False, methods=['get'], url_path='search-clients')
    def search_clients(self, request):
        """
        Busca clientes por nombre, apellido o número de teléfono.

        GET /api/v1/auth/admin/users/search-clients/?query=...

        Query params:
            - query: Texto a buscar (nombre, apellido o teléfono)

        Returns:
            Lista de hasta 10 usuarios que coinciden con la búsqueda.
            Excluye usuarios marcados como Persona Non Grata.
        """
        from django.db.models import Q

        query = request.query_params.get('query', '').strip()
        if not query or len(query) < 2:
            return Response(
                {'error': 'Se requiere un texto de búsqueda con al menos 2 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Buscar clientes y VIPs que coincidan con nombre, apellido o teléfono
        users = CustomUser.objects.filter(
            Q(phone_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query),
            role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
            is_persona_non_grata=False,
            is_active=True,
        ).select_related('profile')[:10]

        # Usar SimpleUserSerializer para la respuesta
        from ..serializers import SimpleUserSerializer
        return Response(SimpleUserSerializer(users, many=True).data)
