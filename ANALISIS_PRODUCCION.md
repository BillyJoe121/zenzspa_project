# Análisis de Completitud y Preparación para Producción - ZenzSpa Backend

# FALTA:

## bot: 

### Lo bueno:
El bot está restringido a usuarios autenticados y rate-limited (bot/views.py (lines 6-40), bot/throttling.py (lines 3-13)). Puede consultar disponibilidad, agendar y cancelar usando los servicios existentes (bot/services.py (lines 14-170)).
### Lo que falta
Falencias frente a RFD-BOT-01/02: i) No existe confirmación explícita previa a ejecutar acciones críticas; ActionExecuteView llamará directamente a execute_action sin un paso de confirmación/human-in-the-loop. ii) No hay guardrails adicionales por rol, ni registro/auditoría de conversaciones o acciones en AuditLog. iii) _cancel_appointment ignora límites de reagendamiento y ventanas de 24h, por lo que los clientes pueden saltarse las políticas mediante el bot (bot/services.py (lines 120-144)).
Configuración y estados

### Bot – 4/10 (no incluido en la media)

ActionExecutorService._cancel_appointment cambia el estado sin pasar por AppointmentService (bot/services.py:129-141), ignorando reglas de 24h, créditos, waitlist y auditoría; reusa los servicios del dominio y registra audit logs.
No hay trazas de quién ejecutó una acción ni límites por tipo de acción, así que una sesión comprometida puede cancelar todas las citas en segundos pese al throttle.
El bot no valida que los IDs de servicio/empleado existan antes de devolver previews útiles, permitiendo enumeration attacks; añade sanitización.
Falta UI/UX para notificar al usuario final cuando la acción falla en backend; hoy sólo se devuelve un error genérico.
Próximos pasos sugeridos