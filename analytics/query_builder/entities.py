"""
Query Builder - Definición de entidades.
"""
from analytics.query_builder.models import FilterField, EntitySchema
from analytics.query_builder.options import (
    USER_ROLE_OPTIONS,
    APPOINTMENT_STATUS_OPTIONS,
    APPOINTMENT_OUTCOME_OPTIONS,
    PAYMENT_STATUS_OPTIONS,
    PAYMENT_TYPE_OPTIONS,
    ORDER_STATUS_OPTIONS,
    DELIVERY_OPTIONS,
)
from analytics.query_builder.types import FieldType


# -----------------------------------------------------------------------------
# ENTIDAD: CLIENTES
# -----------------------------------------------------------------------------
CLIENTS_ENTITY = EntitySchema(
    key="clients",
    label="Clientes",
    icon="👤",
    description="Consulta de clientes y usuarios VIP",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="role",
            label="Rol",
            field_type=FieldType.SELECT,
            db_field="role",
            options=USER_ROLE_OPTIONS,
        ),
        FilterField(
            key="is_vip_active",
            label="Es VIP Activo",
            field_type=FieldType.BOOLEAN,
            db_field="__computed_is_vip",
            help_text="Usuario con membresía VIP vigente",
        ),
        FilterField(
            key="vip_expires_at",
            label="VIP Expira",
            field_type=FieldType.DATE,
            db_field="vip_expires_at",
        ),
        FilterField(
            key="date_joined",
            label="Fecha de Registro",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="last_appointment_date",
            label="Última Cita",
            field_type=FieldType.DATE,
            db_field="__computed_last_appointment",
            help_text="Fecha de la última cita completada",
        ),
        FilterField(
            key="total_appointments",
            label="Total Citas",
            field_type=FieldType.NUMBER,
            db_field="__computed_total_appointments",
        ),
        FilterField(
            key="completed_appointments",
            label="Citas Completadas",
            field_type=FieldType.NUMBER,
            db_field="__computed_completed_appointments",
        ),
        FilterField(
            key="total_spent",
            label="Total Gastado",
            field_type=FieldType.MONEY,
            db_field="__computed_total_spent",
        ),
        FilterField(
            key="is_persona_non_grata",
            label="Bloqueado",
            field_type=FieldType.BOOLEAN,
            db_field="is_persona_non_grata",
        ),
        FilterField(
            key="has_email",
            label="Tiene Email",
            field_type=FieldType.BOOLEAN,
            db_field="__computed_has_email",
        ),
        FilterField(
            key="search",
            label="Buscar",
            field_type=FieldType.TEXT,
            db_field="__search",
            help_text="Busca por nombre, email o teléfono",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: CITAS
# -----------------------------------------------------------------------------
APPOINTMENTS_ENTITY = EntitySchema(
    key="appointments",
    label="Citas",
    icon="📅",
    description="Reservas y citas de servicios",
    default_ordering="-start_time",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.MULTI_SELECT,
            db_field="status",
            options=APPOINTMENT_STATUS_OPTIONS,
        ),
        FilterField(
            key="outcome",
            label="Resultado",
            field_type=FieldType.SELECT,
            db_field="outcome",
            options=APPOINTMENT_OUTCOME_OPTIONS,
        ),
        FilterField(
            key="date",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="start_time",
        ),
        FilterField(
            key="staff_member",
            label="Staff Asignado",
            field_type=FieldType.SELECT,
            db_field="staff_member_id",
            options=[],  # Se llena dinámicamente
        ),
        FilterField(
            key="total_amount",
            label="Monto Total",
            field_type=FieldType.MONEY,
            db_field="price_at_purchase",
        ),
        FilterField(
            key="reschedule_count",
            label="Reagendamientos",
            field_type=FieldType.NUMBER,
            db_field="reschedule_count",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
            help_text="Busca por nombre o teléfono del cliente",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: PAGOS
# -----------------------------------------------------------------------------
PAYMENTS_ENTITY = EntitySchema(
    key="payments",
    label="Pagos",
    icon="💳",
    description="Transacciones y pagos",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.SELECT,
            db_field="status",
            options=PAYMENT_STATUS_OPTIONS,
        ),
        FilterField(
            key="payment_type",
            label="Tipo de Pago",
            field_type=FieldType.MULTI_SELECT,
            db_field="payment_type",
            options=PAYMENT_TYPE_OPTIONS,
        ),
        FilterField(
            key="amount",
            label="Monto",
            field_type=FieldType.MONEY,
            db_field="amount",
        ),
        FilterField(
            key="created_at",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: ÓRDENES
# -----------------------------------------------------------------------------
ORDERS_ENTITY = EntitySchema(
    key="orders",
    label="Órdenes",
    icon="🛒",
    description="Compras del marketplace",
    default_ordering="-created_at",
    filters=[
        FilterField(
            key="status",
            label="Estado",
            field_type=FieldType.MULTI_SELECT,
            db_field="status",
            options=ORDER_STATUS_OPTIONS,
        ),
        FilterField(
            key="delivery_option",
            label="Tipo de Entrega",
            field_type=FieldType.SELECT,
            db_field="delivery_option",
            options=DELIVERY_OPTIONS,
        ),
        FilterField(
            key="total_amount",
            label="Monto Total",
            field_type=FieldType.MONEY,
            db_field="total_amount",
        ),
        FilterField(
            key="shipping_cost",
            label="Costo de Envío",
            field_type=FieldType.MONEY,
            db_field="shipping_cost",
        ),
        FilterField(
            key="created_at",
            label="Fecha",
            field_type=FieldType.DATE,
            db_field="created_at",
        ),
        FilterField(
            key="client_search",
            label="Buscar Cliente",
            field_type=FieldType.TEXT,
            db_field="__client_search",
        ),
    ],
)


# -----------------------------------------------------------------------------
# ENTIDAD: SERVICIOS
# -----------------------------------------------------------------------------
SERVICES_ENTITY = EntitySchema(
    key="services",
    label="Servicios",
    icon="💆",
    description="Catálogo de servicios",
    default_ordering="name",
    filters=[
        FilterField(
            key="category",
            label="Categoría",
            field_type=FieldType.SELECT,
            db_field="category_id",
            options=[],  # Se llena dinámicamente
        ),
        FilterField(
            key="price",
            label="Precio",
            field_type=FieldType.MONEY,
            db_field="price",
        ),
        FilterField(
            key="duration",
            label="Duración (minutos)",
            field_type=FieldType.NUMBER,
            db_field="duration",
        ),
        FilterField(
            key="is_active",
            label="Activo",
            field_type=FieldType.BOOLEAN,
            db_field="is_active",
        ),
        FilterField(
            key="search",
            label="Buscar",
            field_type=FieldType.TEXT,
            db_field="__search",
        ),
    ],
)


ALL_ENTITIES = [
    CLIENTS_ENTITY,
    APPOINTMENTS_ENTITY,
    PAYMENTS_ENTITY,
    ORDERS_ENTITY,
    SERVICES_ENTITY,
]
