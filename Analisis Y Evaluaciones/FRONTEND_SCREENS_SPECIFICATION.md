# 📱 ESPECIFICACIÓN COMPLETA DE PANTALLAS FRONTEND - STUDIOZENS

## 📋 CONVENCIONES DEL DOCUMENTO

- **Endpoint GET**: Endpoint que carga/presenta la pantalla
- **Endpoint POST/PUT/DELETE**: Endpoints que la pantalla invoca
- **Backend Files**: Archivos del backend que sirven/procesan esta pantalla
- **Popups/Modals**: Ventanas emergentes que abre esta pantalla
- **Navegación**: A qué pantallas lleva
- **Componentes**: Elementos UI principales

---

# 🔵 SECCIÓN 1: USUARIO

## 1.1 USUARIOS ANÓNIMOS / NO VERIFICADOS

---

### SCREEN-001: Landing Page / Home

**Ruta Frontend:** `/`

**Descripción:** Página principal pública del spa con información general y CTAs.

**Backend Files:**
- `spa/views/` (catálogo público)
- `spa/models/appointment.py` → `Service`, `ServiceCategory`
- `spa/urls_catalog.py`

**Endpoints GET:**
- `GET /api/v1/catalog/services/` → Lista de servicios activos
- `GET /api/v1/catalog/categories/` → Lista de categorías

**Componentes:**
- Hero section con CTA "Agendar Cita"
- Sección de servicios destacados (cards)
- Sección de productos destacados (cards)
- Testimonios (estático o CMS)
- Footer con información de contacto
- Header con navegación y botón Login/Register
- Widget de chat del bot (minimizado)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Agendar Cita" | Navegar | `/book` o `/login` si no auth |
| "Ver Servicios" | Navegar | `/services` |
| "Tienda" | Navegar | `/shop` |
| "Iniciar Sesión" | Navegar | `/login` |
| "Registrarse" | Navegar | `/register` |
| Chat icon | Abrir | Widget de bot expandido |

---

### SCREEN-002: Catálogo de Servicios (Público)

**Ruta Frontend:** `/services`

**Descripción:** Lista completa de servicios disponibles para consulta pública.

**Backend Files:**
- `spa/views/` → Vistas de catálogo
- `spa/serializers/` → Serializadores públicos
- `spa/models/appointment.py` → `Service`, `ServiceCategory`

**Endpoints GET:**
- `GET /api/v1/catalog/services/` → Todos los servicios
- `GET /api/v1/catalog/services/?category={id}` → Filtrado por categoría

**Componentes:**
- Sidebar con filtros por categoría
- Grid de cards de servicios
- Cada card: imagen, nombre, duración, precio
- Barra de búsqueda (client-side filter)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card de servicio | Navegar | `/services/{id}` |
| "Reservar" en card | Navegar | `/book?service={id}` o `/login` |
| Filtro categoría | Filtrar | Misma página filtrada |

---

### SCREEN-003: Detalle de Servicio (Público)

**Ruta Frontend:** `/services/{id}`

**Descripción:** Información detallada de un servicio específico.

**Backend Files:**
- `spa/views/` 
- `spa/models/appointment.py` → `Service`

**Endpoints GET:**
- `GET /api/v1/catalog/services/{id}/`

**Componentes:**
- Imagen grande del servicio
- Nombre y descripción completa
- Duración y precio (VIP si aplica)
- Categoría
- Botón CTA "Reservar Este Servicio"
- Servicios relacionados (misma categoría)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Reservar Este Servicio" | Navegar | `/book?service={id}` o `/login` |
| Servicio relacionado | Navegar | `/services/{otro-id}` |

---

### SCREEN-004: Tienda / Catálogo de Productos (Público)

**Ruta Frontend:** `/shop`

**Descripción:** Catálogo de productos para venta.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/serializers.py`
- `marketplace/models.py` → `Product`, `ProductVariant`, `ProductImage`

**Endpoints GET:**
- `GET /api/v1/marketplace/products/` → Lista de productos
- `GET /api/v1/marketplace/products/?category={id}` → Filtrado

**Componentes:**
- Grid de productos
- Cada card: imagen principal, nombre, precio desde, stock badge
- Sidebar de filtros (categoría, precio)
- Ordenamiento (precio, nombre, nuevos)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card de producto | Navegar | `/shop/{id}` |
| "Agregar al carrito" | Requiere login | `/login` |

---

### SCREEN-005: Detalle de Producto (Público)

**Ruta Frontend:** `/shop/{id}`

**Descripción:** Información detallada de un producto.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/models.py` → `Product`, `ProductVariant`, `ProductImage`

**Endpoints GET:**
- `GET /api/v1/marketplace/products/{id}/`

**Componentes:**
- Galería de imágenes (carousel)
- Nombre y descripción
- Selector de variante (dropdown)
- Precio (normal y VIP si corresponde)
- Stock disponible
- Selector de cantidad
- Botón "Agregar al Carrito"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Selector variante | Actualizar precio/stock | Misma página |
| +/- cantidad | Actualizar cantidad | Misma página |
| "Agregar al Carrito" | Requiere login | `/login` o agregar a cart |

---

### SCREEN-006: Registro de Usuario

**Ruta Frontend:** `/register`

**Descripción:** Formulario de registro de nuevo usuario.

**Backend Files:**
- `users/views.py` → `UserRegistrationView`
- `users/serializers.py` → `UserRegistrationSerializer`
- `users/models.py` → `CustomUser`
- `users/services.py` → `TwilioService`

**Endpoints POST:**
- `POST /api/v1/users/register/`

**Componentes:**
- Formulario:
  - Input teléfono (+57...)
  - Input nombre
  - Input apellido
  - Input email (opcional)
  - Input contraseña
  - Input confirmar contraseña
  - Checkbox términos y condiciones
  - reCAPTCHA (si aplica)
- Botón "Registrarse"
- Link "¿Ya tienes cuenta? Inicia sesión"

**Validaciones Frontend:**
- Teléfono formato E.164
- Contraseña: 8+ chars, mayúscula, minúscula, número, símbolo
- Confirmación coincide
- Términos aceptados

**Popups/Modals:**
- Modal de términos y condiciones (texto de ConsentTemplate)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Registrarse" | POST registro | `/verify-otp` si éxito |
| "Iniciar sesión" | Navegar | `/login` |
| "Ver términos" | Abrir modal | Modal términos |

**Errores Manejados:**
- "Un usuario con este número ya existe"
- "Este número está bloqueado"
- "Contraseña insegura"
- "Se requiere verificación reCAPTCHA"

---

### SCREEN-007: Verificación OTP

**Ruta Frontend:** `/verify-otp`

**Descripción:** Ingreso del código OTP enviado por SMS.

**Backend Files:**
- `users/views.py` → `VerifySMSView`
- `users/serializers.py` → `VerifySMSSerializer`
- `users/services.py` → `TwilioService`

**Endpoints POST:**
- `POST /api/v1/users/verify-sms/`
- `POST /api/v1/users/resend-otp/` (para reenvío)

**Componentes:**
- Mensaje "Código enviado a +57300***4567"
- Input de 6 dígitos (puede ser 6 inputs separados)
- Timer de expiración
- Botón "Verificar"
- Link "Reenviar código" (con cooldown)
- reCAPTCHA (si múltiples intentos)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Verificar" | POST verificar | `/dashboard` si éxito |
| "Reenviar código" | POST reenviar | Misma página, nuevo código |
| "Cambiar número" | Navegar | `/register` |

**Errores Manejados:**
- "Código inválido o expirado"
- "Demasiados intentos. Espera X minutos"
- "Completa reCAPTCHA"

---

### SCREEN-008: Inicio de Sesión

**Ruta Frontend:** `/login`

**Descripción:** Formulario de autenticación.

**Backend Files:**
- `users/views.py` → `CustomTokenObtainPairView`
- `users/serializers.py` → `CustomTokenObtainPairSerializer`

**Endpoints POST:**
- `POST /api/v1/users/token/`

**Componentes:**
- Input teléfono
- Input contraseña
- Checkbox "Recordarme"
- reCAPTCHA (si múltiples intentos)
- Botón "Iniciar Sesión"
- Link "¿Olvidaste tu contraseña?"
- Link "¿No tienes cuenta? Regístrate"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Iniciar Sesión" | POST login | `/dashboard` o `/verify-2fa` |
| "Olvidé contraseña" | Navegar | `/forgot-password` |
| "Regístrate" | Navegar | `/register` |

**Errores Manejados:**
- "Credenciales inválidas"
- "Número no verificado" (con opción de reenviar)
- "Completa reCAPTCHA"

---

### SCREEN-009: Verificación 2FA (TOTP)

**Ruta Frontend:** `/verify-2fa`

**Descripción:** Ingreso de código TOTP para usuarios con 2FA activo.

**Backend Files:**
- `users/views.py` → `TOTPVerifyView`
- `users/serializers.py` → `TOTPVerifySerializer`
- `users/services.py` → `TOTPService`

**Endpoints POST:**
- `POST /api/v1/users/totp/verify/`

**Componentes:**
- Mensaje "Ingresa el código de tu app autenticadora"
- Input de 6 dígitos
- Botón "Verificar"
- Link "¿Perdiste acceso? Contacta soporte"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Verificar" | POST verificar | `/dashboard` si éxito |

---

### SCREEN-010: Recuperar Contraseña - Solicitud

**Ruta Frontend:** `/forgot-password`

**Descripción:** Solicitar código de recuperación.

**Backend Files:**
- `users/views.py` → `PasswordResetRequestView`
- `users/serializers.py` → `PasswordResetRequestSerializer`

**Endpoints POST:**
- `POST /api/v1/users/password-reset/request/`

**Componentes:**
- Input teléfono
- reCAPTCHA (si aplica)
- Botón "Enviar Código"
- Link "Volver a inicio de sesión"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Enviar Código" | POST | `/reset-password` |
| "Volver" | Navegar | `/login` |

---

### SCREEN-011: Recuperar Contraseña - Confirmar

**Ruta Frontend:** `/reset-password`

**Descripción:** Ingresar código y nueva contraseña.

**Backend Files:**
- `users/views.py` → `PasswordResetConfirmView`
- `users/serializers.py` → `PasswordResetConfirmSerializer`

**Endpoints POST:**
- `POST /api/v1/users/password-reset/confirm/`

**Componentes:**
- Input código OTP
- Input nueva contraseña
- Input confirmar contraseña
- Indicador de fortaleza de contraseña
- Botón "Restablecer Contraseña"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Restablecer" | POST | `/login` con mensaje éxito |

---

### SCREEN-012: Widget de Chat Bot (Público)

**Ruta Frontend:** Componente flotante en todas las páginas públicas

**Descripción:** Chat con el asistente virtual.

**Backend Files:**
- `bot/views/webhook.py` → Webhook de entrada
- `bot/services.py` → `PromptOrchestrator`, `GeminiService`
- `bot/models/conversation.py` → `AnonymousUser`, `BotConversationLog`

**Endpoints POST:**
- `POST /api/v1/bot/webhook/` (para WhatsApp)
- `POST /api/v1/bot/chat/` (para widget web)

**Componentes:**
- Botón flotante (minimizado)
- Panel de chat expandible
- Lista de mensajes (burbujas)
- Input de mensaje
- Botón enviar
- Indicador "escribiendo..."
- Botón minimizar

**Estados:**
- Minimizado (solo icono)
- Expandido (panel de chat)
- Cargando respuesta

---

### SCREEN-013: Pantalla de Kiosk (Modo Tableta)

**Ruta Frontend:** `/kiosk/{token}`

**Descripción:** Interfaz especial para que clientes completen su perfil en tableta del spa.

**Backend Files:**
- `profiles/views.py` → `KioskSessionStatusView`, `DoshaQuizSubmitView`
- `profiles/permissions.py` → `IsKioskSession`
- `profiles/models.py` → `KioskSession`
- `profiles/serializers.py` → `KioskSessionStatusSerializer`

**Endpoints GET:**
- `GET /api/v1/kiosk/status/` (con header X-Kiosk-Token)
- `GET /api/v1/profiles/dosha-questions/`

**Endpoints POST:**
- `POST /api/v1/profiles/dosha-quiz/submit/`
- `POST /api/v1/kiosk/heartbeat/`
- `POST /api/v1/kiosk/lock/`

**Componentes:**
- Header con timer de sesión
- Bienvenida personalizada con nombre del cliente
- Cuestionario Dosha (wizard multi-step)
- Cada pregunta con opciones de radio
- Barra de progreso
- Botones Anterior/Siguiente
- Pantalla de resultado final
- Pantalla segura (cuando expira/bloquea)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Siguiente" | Avanzar pregunta | Siguiente step |
| "Anterior" | Retroceder | Step anterior |
| "Enviar" | POST quiz | Pantalla resultado |
| Timer expira | Auto-lock | Pantalla segura |

**Popups/Modals:**
- Modal "Cambios sin guardar" si intenta salir
- Modal "Sesión expirada"

---

## 1.2 USUARIOS REGISTRADOS (CLIENT / VIP)

---

### SCREEN-014: Dashboard del Cliente

**Ruta Frontend:** `/dashboard`

**Descripción:** Panel principal del usuario autenticado.

**Backend Files:**
- `users/views.py` → `CurrentUserView`
- `spa/views/appointments.py` → Lista de citas del usuario
- `marketplace/views.py` → Órdenes del usuario
- `spa/models/voucher.py` → Vouchers del usuario

**Endpoints GET:**
- `GET /api/v1/users/me/`
- `GET /api/v1/appointments/?status=upcoming`
- `GET /api/v1/orders/?status=active`
- `GET /api/v1/vouchers/?status=available`
- `GET /api/v1/credits/balance/`

**Componentes:**
- Saludo personalizado "Hola, {nombre}"
- Badge VIP si aplica
- Card "Próxima Cita" con countdown
- Cards resumen:
  - Citas activas (count)
  - Vouchers disponibles (count)
  - Crédito a favor (monto)
  - Órdenes en proceso (count)
- Accesos rápidos:
  - Agendar cita
  - Ver mis citas
  - Tienda
  - Mi perfil

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Agendar Cita" | Navegar | `/book` |
| "Ver Citas" | Navegar | `/appointments` |
| "Ir a Tienda" | Navegar | `/shop` |
| "Mi Perfil" | Navegar | `/profile` |
| Card próxima cita | Navegar | `/appointments/{id}` |

---

### SCREEN-015: Agendar Cita - Selección de Servicios

**Ruta Frontend:** `/book`

**Descripción:** Paso 1 del flujo de reserva: seleccionar servicios.

**Backend Files:**
- `spa/views/` → Catálogo
- `spa/models/appointment.py` → `Service`, `ServiceCategory`

**Endpoints GET:**
- `GET /api/v1/catalog/services/`

**Componentes:**
- Lista de servicios agrupados por categoría
- Checkbox múltiple para seleccionar
- Resumen lateral:
  - Servicios seleccionados
  - Duración total
  - Precio total (VIP si aplica)
- Botón "Continuar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Checkbox servicio | Agregar/quitar | Actualizar resumen |
| "Continuar" | Navegar | `/book/availability` |
| "Cancelar" | Navegar | `/dashboard` |

---

### SCREEN-016: Agendar Cita - Selección de Fecha/Hora

**Ruta Frontend:** `/book/availability`

**Descripción:** Paso 2: seleccionar fecha, hora y staff.

**Backend Files:**
- `spa/services/appointments.py` → `AvailabilityService`
- `spa/models/appointment.py` → `StaffAvailability`, `AvailabilityExclusion`

**Endpoints GET:**
- `GET /api/v1/appointments/availability/?services={ids}&date={date}`

**Componentes:**
- Calendario para seleccionar fecha
- Grid de slots disponibles
- Cada slot muestra hora y nombre del staff
- Filtro opcional por staff
- Resumen de selección
- Botón "Continuar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Fecha en calendario | Cargar slots | Actualizar grid |
| Slot disponible | Seleccionar | Marcar seleccionado |
| Filtro staff | Filtrar | Actualizar slots |
| "Continuar" | Navegar | `/book/confirm` |
| "Atrás" | Navegar | `/book` |

---

### SCREEN-017: Agendar Cita - Confirmación

**Ruta Frontend:** `/book/confirm`

**Descripción:** Paso 3: revisar y confirmar reserva.

**Backend Files:**
- `spa/services/appointments.py` → `AppointmentService`
- `spa/services/payments.py` → `PaymentService`
- `spa/models/payment.py` → `Payment`, `ClientCredit`

**Endpoints GET:**
- `GET /api/v1/credits/balance/`

**Endpoints POST:**
- `POST /api/v1/appointments/`

**Componentes:**
- Resumen completo:
  - Servicios con precios
  - Fecha y hora
  - Staff asignado
  - Duración total
  - Precio total
  - Monto anticipo (20%)
- Sección de crédito disponible (si hay)
  - Toggle "Usar crédito"
  - Monto a aplicar
- Sección de voucher (si aplica)
  - Input código voucher
  - Botón "Aplicar"
- Total a pagar
- Checkbox términos
- Botón "Confirmar y Pagar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Toggle crédito | Actualizar total | Misma página |
| "Aplicar voucher" | Validar voucher | Actualizar total |
| "Confirmar y Pagar" | POST + redirect | Wompi o `/appointments/success` |
| "Atrás" | Navegar | `/book/availability` |

**Popups/Modals:**
- Modal de términos de servicio
- Modal de error si voucher inválido

---

### SCREEN-018: Pago en Wompi (Externa)

**Ruta Frontend:** Redirección a `checkout.wompi.co`

**Descripción:** Página de pago de Wompi (no controlamos).

**Backend Files:**
- `finances/gateway.py` → `WompiPaymentClient`
- `spa/services/payments.py` → Generación de firma

**Flujo:**
1. Usuario llega a checkout Wompi
2. Completa pago (tarjeta, PSE, Nequi, etc.)
3. Wompi redirige a `WOMPI_REDIRECT_URL`

---

### SCREEN-019: Resultado de Pago

**Ruta Frontend:** `/payment-result`

**Descripción:** Página de retorno después del pago.

**Backend Files:**
- Lógica en frontend que consulta estado
- `spa/models/payment.py` → `Payment`

**Endpoints GET:**
- `GET /api/v1/payments/{id}/status/`

**Componentes:**
- Estado de pago:
  - ✅ Aprobado: Mensaje de éxito + detalles de cita
  - ❌ Rechazado: Mensaje de error + opción reintentar
  - ⏳ Pendiente: Mensaje de espera + polling

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Ver Mi Cita" (éxito) | Navegar | `/appointments/{id}` |
| "Reintentar Pago" (fallo) | Navegar | `/book/confirm` |
| "Ir al Dashboard" | Navegar | `/dashboard` |

---

### SCREEN-020: Lista de Mis Citas

**Ruta Frontend:** `/appointments`

**Descripción:** Historial y citas activas del usuario.

**Backend Files:**
- `spa/views/appointments.py`
- `spa/models/appointment.py` → `Appointment`

**Endpoints GET:**
- `GET /api/v1/appointments/my/`
- Parámetros: `?status=upcoming|past|all`

**Componentes:**
- Tabs: Próximas / Pasadas / Todas
- Lista de cards de citas:
  - Fecha y hora
  - Servicios
  - Staff
  - Estado (badge de color)
  - Acciones contextuales

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card de cita | Navegar | `/appointments/{id}` |
| "Agendar Nueva" | Navegar | `/book` |
| Tab | Filtrar | Misma página filtrada |

---

### SCREEN-021: Detalle de Cita

**Ruta Frontend:** `/appointments/{id}`

**Descripción:** Información completa de una cita.

**Backend Files:**
- `spa/views/appointments.py`
- `spa/models/appointment.py` → `Appointment`, `AppointmentItem`
- `spa/models/payment.py` → `Payment`

**Endpoints GET:**
- `GET /api/v1/appointments/{id}/`

**Endpoints POST/PUT:**
- `PUT /api/v1/appointments/{id}/reschedule/`
- `POST /api/v1/appointments/{id}/cancel/`

**Componentes:**
- Fecha, hora, duración
- Servicios incluidos con precios
- Staff asignado
- Estado actual (badge)
- Pagos realizados
- Saldo pendiente (si hay)
- Botones de acción según estado:
  - PENDING_PAYMENT: "Pagar Ahora"
  - CONFIRMED: "Reagendar", "Cancelar"
  - PAID: Info de pago
  - COMPLETED: "Agregar Propina"
- Timeline de eventos

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Pagar Ahora" | Redirect | Wompi |
| "Reagendar" | Abrir modal | Modal selección fecha |
| "Cancelar" | Abrir modal | Modal confirmación |
| "Agregar al Calendario" | Descargar | Archivo .ics |
| "Agregar Propina" | Abrir modal | Modal propina |

**Popups/Modals:**
- Modal de reagendamiento (calendario + slots)
- Modal de confirmación de cancelación
- Modal de propina (monto + pago)

---

### SCREEN-022: Mi Perfil Clínico

**Ruta Frontend:** `/profile`

**Descripción:** Vista del perfil clínico del usuario.

**Backend Files:**
- `profiles/views.py` → `ClinicalProfileViewSet`
- `profiles/models.py` → `ClinicalProfile`, `LocalizedPain`
- `profiles/serializers.py` → `ClinicalProfileSerializer`

**Endpoints GET:**
- `GET /api/v1/profiles/me/`

**Componentes:**
- Dosha dominante con descripción
- Elemento asociado
- Información de estilo de vida:
  - Tipo de dieta
  - Calidad de sueño
  - Nivel de actividad
- Lista de dolores localizados
- Condiciones médicas (solo visible para el usuario)
- Alergias
- Contraindicaciones
- Acciones: Editar, Completar cuestionario

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Editar Perfil" | Navegar | `/profile/edit` |
| "Hacer Cuestionario Dosha" | Navegar | `/profile/dosha-quiz` |
| "Ver Historial" | Navegar | `/profile/history` |
| "Mis Consentimientos" | Navegar | `/profile/consents` |

---

### SCREEN-023: Editar Perfil Clínico

**Ruta Frontend:** `/profile/edit`

**Descripción:** Formulario de edición del perfil.

**Backend Files:**
- `profiles/views.py` → `ClinicalProfileViewSet.update`
- `profiles/serializers.py` → `ClinicalProfileSerializer`

**Endpoints PUT/PATCH:**
- `PATCH /api/v1/profiles/me/`

**Componentes:**
- Formulario con campos:
  - Tipo de dieta (dropdown)
  - Calidad de sueño (dropdown)
  - Nivel de actividad (dropdown)
  - Condiciones médicas (textarea encriptado)
  - Alergias (textarea encriptado)
  - Contraindicaciones (textarea encriptado)
  - Notas de accidentes (textarea encriptado)
- Lista editable de dolores localizados
- Botón "Agregar Dolor"
- Botón "Guardar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Agregar Dolor" | Expandir | Formulario de dolor inline |
| "Eliminar" en dolor | Quitar | Eliminar de lista |
| "Guardar" | PATCH | `/profile` con mensaje |
| "Cancelar" | Navegar | `/profile` |

---

### SCREEN-024: Cuestionario Dosha

**Ruta Frontend:** `/profile/dosha-quiz`

**Descripción:** Wizard para determinar el dosha dominante.

**Backend Files:**
- `profiles/views.py` → `DoshaQuestionListView`, `DoshaQuizSubmitView`
- `profiles/models.py` → `DoshaQuestion`, `DoshaOption`, `ClientDoshaAnswer`
- `profiles/services.py` → `calculate_dominant_dosha_and_element`

**Endpoints GET:**
- `GET /api/v1/profiles/dosha-questions/`

**Endpoints POST:**
- `POST /api/v1/profiles/dosha-quiz/submit/`

**Componentes:**
- Wizard multi-step (1 pregunta por paso)
- Pregunta con opciones de radio
- Barra de progreso
- Navegación anterior/siguiente
- Contador de preguntas (5/10)
- Página final de resultado

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Siguiente" | Avanzar | Siguiente pregunta |
| "Anterior" | Retroceder | Pregunta anterior |
| "Ver Resultado" | POST | Página de resultado |

---

### SCREEN-025: Resultado Dosha

**Ruta Frontend:** `/profile/dosha-result`

**Descripción:** Resultado del cuestionario dosha.

**Componentes:**
- Dosha dominante con imagen
- Descripción del dosha
- Elemento asociado
- Scores por dosha (gráfico)
- Recomendaciones personalizadas
- Servicios sugeridos
- Botón "Ver Servicios Recomendados"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Ver Servicios" | Navegar | `/services?dosha={dosha}` |
| "Volver a Mi Perfil" | Navegar | `/profile` |

---







### SCREEN-026: Mis Consentimientos

**Ruta Frontend:** `/profile/consents`

**Descripción:** Lista de consentimientos firmados y pendientes.

**Backend Files:**
- `profiles/views.py` → `SignConsentView`
- `profiles/models.py` → `ConsentTemplate`, `ConsentDocument`

**Endpoints GET:**
- `GET /api/v1/profiles/consent-templates/` (activos)
- `GET /api/v1/profiles/me/consents/` (firmados)

**Endpoints POST:**
- `POST /api/v1/profiles/consents/sign/`

**Componentes:**
- Lista de consentimientos firmados:
  - Versión
  - Fecha de firma
  - Hash de firma
- Consentimientos pendientes (nueva versión)
- Botón "Firmar" para pendientes

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Firmar" | Abrir modal | Modal de firma |
| "Ver Documento" | Abrir modal | Modal con texto legal |

**Popups/Modals:**
- Modal de documento legal completo
- Modal de confirmación de firma

---

### SCREEN-027: Exportar Mis Datos (GDPR)

**Ruta Frontend:** `/settings/privacy`

**Descripción:** Configuración de privacidad y exportación GDPR.

**Backend Files:**
- `profiles/views.py` → `ExportClinicalDataView`

**Endpoints GET:**
- `GET /api/v1/profiles/me/export/`

**Componentes:**
- Información sobre derechos GDPR
- Botón "Exportar Todos Mis Datos"
- Historial de exportaciones
- Botón "Solicitar Eliminación" (abre formulario)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Exportar Datos" | GET + download | Archivo JSON |
| "Solicitar Eliminación" | Abrir modal | Modal de solicitud |

---

### SCREEN-028: Mis Vouchers

**Ruta Frontend:** `/vouchers`

**Descripción:** Lista de vouchers del usuario.

**Backend Files:**
- `spa/models/voucher.py` → `Voucher`, `UserPackage`

**Endpoints GET:**
- `GET /api/v1/vouchers/my/`

**Componentes:**
- Tabs: Disponibles / Usados / Expirados
- Cards de vouchers:
  - Código
  - Servicio asociado
  - Fecha de expiración
  - Estado (badge)
  - Paquete de origen (si aplica)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Usar Voucher" | Navegar | `/book?voucher={code}` |
| "Ver Paquete" | Navegar | `/packages/{id}` |
| Tab | Filtrar | Misma página |

---











### SCREEN-029: Paquetes Disponibles

**Ruta Frontend:** `/packages`

**Descripción:** Catálogo de paquetes para compra.

**Backend Files:**
- `spa/views/packages.py`
- `spa/models/voucher.py` → `Package`, `PackageService`

**Endpoints GET:**
- `GET /api/v1/packages/`

**Componentes:**
- Grid de paquetes:
  - Nombre y descripción
  - Servicios incluidos
  - Precio
  - Ahorro vs individual
  - Meses VIP incluidos (si aplica)
  - Validez

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card paquete | Navegar | `/packages/{id}` |
| "Comprar" | Navegar | `/packages/{id}/checkout` |

---

### SCREEN-030: Detalle y Compra de Paquete

**Ruta Frontend:** `/packages/{id}`

**Descripción:** Detalle de paquete con opción de compra.

**Backend Files:**
- `spa/views/packages.py`
- `spa/services/vouchers.py` → `PackagePurchaseService`

**Endpoints GET:**
- `GET /api/v1/packages/{id}/`

**Endpoints POST:**
- `POST /api/v1/packages/{id}/purchase/`

**Componentes:**
- Detalle completo del paquete
- Lista de servicios incluidos con cantidades
- Precio y ahorro
- Fecha de expiración de vouchers
- Términos de uso
- Botón "Comprar Ahora"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Comprar Ahora" | POST + redirect | Wompi |

---

### SCREEN-031: Suscripción VIP

**Ruta Frontend:** `/vip`

**Descripción:** Información y suscripción a membresía VIP.

**Backend Files:**
- `spa/services/vip.py` → `VipSubscriptionService`
- `core/models.py` → `GlobalSettings.vip_monthly_price`
- `users/models.py` → Campos VIP

**Endpoints GET:**
- `GET /api/v1/vip/info/`
- `GET /api/v1/users/me/` (estado VIP)

**Endpoints POST:**
- `POST /api/v1/vip/subscribe/`

**Componentes:**
- Beneficios VIP listados
- Precio mensual
- Comparación CLIENT vs VIP
- Estado actual si ya es VIP:
  - Fecha de expiración
  - Renovación automática (toggle)
- Botón "Suscribirme"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Suscribirme" | POST + redirect | Wompi |
| Toggle renovación | PUT | Actualizar preferencia |
| "Cancelar Renovación" | PUT | Confirmar cancelación |

---

### SCREEN-032: Mi Carrito de Compras

**Ruta Frontend:** `/cart`

**Descripción:** Carrito de productos del marketplace.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/models.py` → `Cart`, `CartItem`

**Endpoints GET:**
- `GET /api/v1/marketplace/cart/`

**Endpoints PUT/DELETE:**
- `PUT /api/v1/marketplace/cart/items/{id}/`
- `DELETE /api/v1/marketplace/cart/items/{id}/`

**Componentes:**
- Lista de items:
  - Imagen miniatura
  - Nombre producto y variante
  - Precio unitario
  - Selector de cantidad (+/-)
  - Subtotal
  - Botón eliminar
- Resumen:
  - Subtotal
  - Envío estimado
  - Total
- Botón "Proceder al Pago"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| +/- cantidad | PUT | Actualizar item |
| "Eliminar" | DELETE | Quitar item |
| "Seguir Comprando" | Navegar | `/shop` |
| "Proceder al Pago" | Navegar | `/checkout` |

---

### SCREEN-033: Checkout de Orden

**Ruta Frontend:** `/checkout`

**Descripción:** Proceso de checkout para marketplace.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/services.py` → `OrderCreationService`
- `marketplace/models.py` → `Order`

**Endpoints POST:**
- `POST /api/v1/marketplace/orders/`

**Componentes:**
- Resumen de productos
- Opciones de entrega:
  - Radio: Envío / Recoger en local / Asociar a cita
- Si envío: formulario de dirección
- Si asociar a cita: selector de citas
- Fecha estimada de entrega
- Resumen de costos
- Botón "Pagar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Radio entrega | Actualizar | Mostrar/ocultar campos |
| "Pagar" | POST + redirect | Wompi |
| "Volver al Carrito" | Navegar | `/cart` |

---

### SCREEN-034: Historial de Órdenes

**Ruta Frontend:** `/orders`

**Descripción:** Lista de órdenes del marketplace.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/models.py` → `Order`, `OrderItem`

**Endpoints GET:**
- `GET /api/v1/marketplace/orders/my/`

**Componentes:**
- Tabs: Activas / Completadas / Todas
- Lista de órdenes:
  - Número de orden
  - Fecha
  - Estado (badge)
  - Total
  - Productos (thumbnails)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card orden | Navegar | `/orders/{id}` |
| Tab | Filtrar | Misma página |

---

### SCREEN-035: Detalle de Orden

**Ruta Frontend:** `/orders/{id}`

**Descripción:** Detalle completo de una orden.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/services.py` → `ReturnService`

**Endpoints GET:**
- `GET /api/v1/marketplace/orders/{id}/`

**Endpoints POST:**
- `POST /api/v1/marketplace/orders/{id}/return/`

**Componentes:**
- Número y fecha de orden
- Estado con timeline
- Lista de productos con precios
- Información de envío
- Tracking number (si aplica)
- Total pagado
- Botón "Solicitar Devolución" (si aplica)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Solicitar Devolución" | Abrir modal | Modal de devolución |
| "Tracking" | Abrir externa | URL de tracking |

**Popups/Modals:**
- Modal de solicitud de devolución:
  - Selector de items a devolver
  - Cantidades
  - Motivo
  - Botón enviar

---

### SCREEN-036: Mi Crédito a Favor

**Ruta Frontend:** `/credits`

**Descripción:** Balance y movimientos de crédito.

**Backend Files:**
- `spa/models/payment.py` → `ClientCredit`, `PaymentCreditUsage`

**Endpoints GET:**
- `GET /api/v1/credits/my/`
- `GET /api/v1/credits/movements/`

**Componentes:**
- Balance total disponible
- Lista de créditos:
  - Monto original
  - Monto restante
  - Origen (devolución, ajuste, etc.)
  - Fecha de expiración
  - Estado

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Usar Crédito" | Navegar | `/book` |

---

### SCREEN-037: Lista de Espera

**Ruta Frontend:** `/waitlist`

**Descripción:** Gestión de entradas en lista de espera.

**Backend Files:**
- `spa/views/waitlist.py`
- `spa/services/waitlist.py` → `WaitlistService`
- `spa/models/appointment.py` → `WaitlistEntry`

**Endpoints GET:**
- `GET /api/v1/waitlist/my/`

**Endpoints POST:**
- `POST /api/v1/waitlist/`

**Componentes:**
- Entradas activas con:
  - Servicios deseados
  - Fecha preferida
  - Estado
  - Oferta pendiente (si hay)
- Formulario para nueva entrada
- Ofertas recibidas (destacadas)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Agregar a Lista" | POST | Agregar entrada |
| "Aceptar Oferta" | POST | Confirmar cita ofrecida |
| "Rechazar Oferta" | POST | Liberar oferta |
| "Eliminar" | DELETE | Quitar de lista |

---

### SCREEN-038: Configuración de Cuenta

**Ruta Frontend:** `/settings`

**Descripción:** Configuración general de la cuenta.

**Backend Files:**
- `users/views.py`
- `notifications/views.py`

**Componentes:**
- Navegación lateral:
  - Perfil
  - Seguridad
  - Notificaciones
  - Privacidad
  - Sesiones
  - Suscripción VIP

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Opción menú | Navegar | Subsección correspondiente |

---

### SCREEN-039: Configuración de Seguridad

**Ruta Frontend:** `/settings/security`

**Descripción:** Opciones de seguridad de la cuenta.

**Backend Files:**
- `users/views.py` → `ChangePasswordView`, `TOTPSetupView`
- `users/services.py` → `TOTPService`

**Endpoints POST:**
- `POST /api/v1/users/change-password/`
- `GET /api/v1/users/totp/setup/`
- `POST /api/v1/users/totp/verify/`

**Componentes:**
- Sección cambiar contraseña:
  - Input contraseña actual
  - Input nueva contraseña
  - Input confirmar
  - Botón "Cambiar"
- Sección 2FA:
  - Estado actual
  - Botón "Activar/Desactivar"
  - QR code (si activando)

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Cambiar Contraseña" | POST | Logout + login |
| "Activar 2FA" | GET setup | Mostrar QR |
| "Verificar 2FA" | POST verify | Confirmar activación |

---

### SCREEN-040: Configuración de Notificaciones

**Ruta Frontend:** `/settings/notifications`

**Descripción:** Preferencias de notificaciones.

**Backend Files:**
- `notifications/views.py`
- `notifications/models.py` → `NotificationPreference`

**Endpoints GET:**
- `GET /api/v1/notifications/preferences/`

**Endpoints PUT:**
- `PUT /api/v1/notifications/preferences/`

**Componentes:**
- Toggle Email habilitado
- Toggle WhatsApp habilitado
- Configuración Quiet Hours:
  - Hora inicio
  - Hora fin
- Selector de timezone
- Botón "Guardar"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Toggles | PUT | Actualizar preferencia |
| "Guardar" | PUT | Guardar configuración |

---

### SCREEN-041: Gestión de Sesiones

**Ruta Frontend:** `/settings/sessions`

**Descripción:** Ver y cerrar sesiones activas.

**Backend Files:**
- `users/views.py` → `UserSessionListView`, `UserSessionDeleteView`, `LogoutAllView`
- `users/models.py` → `UserSession`

**Endpoints GET:**
- `GET /api/v1/users/sessions/`

**Endpoints DELETE:**
- `DELETE /api/v1/users/sessions/{id}/`
- `POST /api/v1/users/logout-all/`

**Componentes:**
- Lista de sesiones:
  - Dispositivo/navegador
  - IP
  - Última actividad
  - Sesión actual (badge)
  - Botón cerrar
- Botón "Cerrar Todas las Sesiones"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Cerrar" en sesión | DELETE | Eliminar sesión |
| "Cerrar Todas" | POST | Logout global |

---

# 🟠 SECCIÓN 2: STAFF Y ADMIN

## 2.1 PANTALLAS COMPARTIDAS

---

### SCREEN-042: Dashboard Staff/Admin

**Ruta Frontend:** `/admin/dashboard`

**Descripción:** Panel principal para personal del spa.

**Backend Files:**
- `analytics/services.py` → `KpiService`
- `spa/views/appointments.py`
- `bot/models/handoff.py` → `HumanHandoffRequest`

**Endpoints GET:**
- `GET /api/v1/analytics/kpis/today/`
- `GET /api/v1/appointments/today/`
- `GET /api/v1/bot/handoffs/?status=pending`
- `GET /api/v1/admin/notifications/unread/`

**Componentes:**
- KPIs del día:
  - Citas de hoy
  - Ingresos del día
  - No-shows
- Lista de citas de hoy con timeline
- Alertas pendientes:
  - Handoffs sin atender
  - Stock bajo
  - Pagos fallidos
- Accesos rápidos

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Card cita | Navegar | `/admin/appointments/{id}` |
| Alerta handoff | Navegar | `/admin/handoffs` |
| Alerta stock | Navegar | `/admin/inventory` |

---

### SCREEN-043: Calendario de Citas (Vista Staff)

**Ruta Frontend:** `/admin/calendar`

**Descripción:** Vista de calendario de todas las citas.

**Backend Files:**
- `spa/views/appointments.py`
- `spa/models/appointment.py` → `Appointment`

**Endpoints GET:**
- `GET /api/v1/appointments/?start_date={}&end_date={}`
- `GET /api/v1/staff/`

**Componentes:**
- Calendario semanal/mensual
- Citas como bloques de color por estado
- Filtro por staff
- Vista de día con slots
- Sidebar con detalles al hacer click

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Bloque de cita | Abrir sidebar | Detalles rápidos |
| "Ver Detalles" | Navegar | `/admin/appointments/{id}` |
| "Nueva Cita" | Abrir modal | Modal creación manual |

---

### SCREEN-044: Lista de Citas (Admin)

**Ruta Frontend:** `/admin/appointments`

**Descripción:** Lista tabular de citas con filtros avanzados.

**Backend Files:**
- `spa/views/appointments.py`

**Endpoints GET:**
- `GET /api/v1/appointments/`
- Filtros: fecha, estado, staff, cliente

**Componentes:**
- Tabla con columnas:
  - Cliente
  - Fecha/hora
  - Servicios
  - Staff
  - Estado
  - Monto
  - Acciones
- Filtros avanzados
- Búsqueda por cliente
- Paginación
- Exportar a CSV

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Fila | Navegar | `/admin/appointments/{id}` |
| "Exportar" | Descargar | CSV |
| Filtros | Aplicar | Misma página filtrada |

---

### SCREEN-045: Detalle de Cita (Admin)

**Ruta Frontend:** `/admin/appointments/{id}`

**Descripción:** Vista completa de cita con acciones admin.

**Backend Files:**
- `spa/views/appointments.py`
- `spa/services/appointments.py` → `AppointmentService`
- `spa/services/payments.py` → `PaymentService`
- `core/models.py` → `AuditLog`

**Endpoints GET:**
- `GET /api/v1/appointments/{id}/`

**Endpoints POST/PUT:**
- `PUT /api/v1/appointments/{id}/reschedule/`
- `POST /api/v1/appointments/{id}/cancel/`
- `POST /api/v1/appointments/{id}/complete/`
- `POST /api/v1/appointments/{id}/no-show/`

**Componentes:**
- Información del cliente (link al perfil)
- Detalles de la cita
- Timeline de eventos
- Pagos asociados
- Historial de cambios
- Acciones según estado:
  - Reagendar (forzado)
  - Cancelar con motivo
  - Completar
  - Marcar no-show
  - Registrar pago final

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Ver Cliente" | Navegar | `/admin/users/{phone}` |
| "Reagendar" | Abrir modal | Modal fecha/hora |
| "Cancelar" | Abrir modal | Modal con motivo |
| "Completar" | Abrir modal | Modal pago final |
| "No-Show" | Abrir modal | Modal confirmación |

**Popups/Modals:**
- Modal de reagendamiento forzado
- Modal de cancelación con motivo
- Modal de registro de pago final
- Modal de confirmación no-show

---

### SCREEN-046: Lista de Usuarios

**Ruta Frontend:** `/admin/users`

**Descripción:** Directorio de usuarios del sistema.

**Backend Files:**
- `users/views.py` → `UserExportView`
- `users/models.py` → `CustomUser`

**Endpoints GET:**
- `GET /api/v1/users/`
- Filtros: rol, estado, VIP, CNG

**Componentes:**
- Tabla con columnas:
  - Nombre
  - Teléfono
  - Email
  - Rol
  - Estado VIP
  - Estado (activo/CNG)
  - Última actividad
- Búsqueda
- Filtros
- Exportar

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Fila | Navegar | `/admin/users/{phone}` |
| "Exportar CSV" | GET | Descargar archivo |
| "Nuevo Staff" | Abrir modal | Modal crear staff |

---

### SCREEN-047: Detalle de Usuario (Admin)

**Ruta Frontend:** `/admin/users/{phone}`

**Descripción:** Vista 360° de un usuario.

**Backend Files:**
- `users/views.py` → `FlagNonGrataView`
- `profiles/views.py`
- `spa/views/appointments.py`
- `marketplace/views.py`

**Endpoints GET:**
- `GET /api/v1/users/{phone}/`
- `GET /api/v1/profiles/{phone}/`
- `GET /api/v1/appointments/?user={id}`
- `GET /api/v1/orders/?user={id}`
- `GET /api/v1/credits/?user={id}`

**Endpoints PUT:**
- `PUT /api/v1/users/{phone}/flag-non-grata/`

**Componentes:**
- Header con info básica y badges
- Tabs:
  - Perfil clínico
  - Citas (historial)
  - Órdenes
  - Pagos
  - Créditos
  - Vouchers
  - Notas internas
- Acciones admin:
  - Editar rol
  - Marcar CNG
  - Ajuste financiero
  - Ver sesiones

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Marcar CNG" | Abrir modal | Modal con notas/foto |
| "Ajuste Financiero" | Abrir modal | Modal crédito/débito |
| "Ver Sesiones" | Navegar | `/admin/users/{phone}/sessions` |
| Tab | Cambiar vista | Misma página, diferente tab |

**Popups/Modals:**
- Modal CNG (notas, foto, confirmación)
- Modal ajuste financiero

---

### SCREEN-048: Perfil Clínico (Vista Staff)

**Ruta Frontend:** `/admin/users/{phone}/profile`

**Descripción:** Vista del perfil clínico con acciones de staff.

**Backend Files:**
- `profiles/views.py` → `ClinicalProfileViewSet`
- `profiles/models.py`

**Endpoints GET:**
- `GET /api/v1/profiles/{phone}/`

**Endpoints PUT:**
- `PUT /api/v1/profiles/{phone}/`

**Componentes:**
- Información clínica completa
- Notas del terapeuta (editables)
- Historial de versiones
- Dolores localizados
- Consentimientos
- Botón "Iniciar Sesión Kiosk"

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Editar Notas" | Inline edit | Guardar notas |
| "Ver Historial" | Navegar | `/admin/profiles/{id}/history` |
| "Iniciar Kiosk" | POST | Generar token kiosk |

---

### SCREEN-049: Gestión de Handoffs

**Ruta Frontend:** `/admin/handoffs`

**Descripción:** Cola de solicitudes de atención humana.

**Backend Files:**
- `bot/views/handoff_api.py`
- `bot/models/handoff.py` → `HumanHandoffRequest`, `HumanMessage`

**Endpoints GET:**
- `GET /api/v1/bot/handoffs/`
- Filtros: status, assigned_to

**Componentes:**
- Tabs: Pendientes / Asignados a mí / Resueltos
- Lista de solicitudes:
  - Cliente (nombre o anónimo)
  - Score
  - Motivo de escalamiento
  - Tiempo de espera
  - Intereses del cliente
- Ordenamiento por score/tiempo

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Tomar" | POST assign | Asignar a mí |
| Fila | Navegar | `/admin/handoffs/{id}` |

---

### SCREEN-050: Chat de Handoff

**Ruta Frontend:** `/admin/handoffs/{id}`

**Descripción:** Interfaz de chat para atender handoff.

**Backend Files:**
- `bot/views/handoff_api.py`
- `bot/models/handoff.py` → `HumanMessage`

**Endpoints GET:**
- `GET /api/v1/bot/handoffs/{id}/`
- `GET /api/v1/bot/handoffs/{id}/messages/`

**Endpoints POST:**
- `POST /api/v1/bot/handoffs/{id}/messages/`
- `POST /api/v1/bot/handoffs/{id}/resolve/`

**Componentes:**
- Panel izquierdo: info del cliente
  - Datos de contacto
  - Intereses detectados
  - Historial de conversación con bot
  - Score
- Panel derecho: chat
  - Mensajes bidireccionales
  - Input de mensaje
  - Botón enviar
- Footer:
  - Notas internas
  - Botón resolver

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Enviar" | POST message | Agregar mensaje |
| "Resolver" | POST resolve | Cerrar handoff |
| "Ver Citas" | Navegar nueva tab | `/admin/users/{phone}` |

---

### SCREEN-051: Gestión de Órdenes

**Ruta Frontend:** `/admin/orders`

**Descripción:** Lista de órdenes del marketplace.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/services.py` → `OrderService`

**Endpoints GET:**
- `GET /api/v1/marketplace/orders/`

**Componentes:**
- Filtros por estado
- Tabla de órdenes:
  - Número
  - Cliente
  - Fecha
  - Estado
  - Total
  - Entrega
- Acciones rápidas por estado

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| Fila | Navegar | `/admin/orders/{id}` |
| "Iniciar Preparación" | POST | Cambiar estado |
| "Marcar Enviado" | Abrir modal | Modal tracking |

---

### SCREEN-052: Detalle de Orden (Admin)

**Ruta Frontend:** `/admin/orders/{id}`

**Descripción:** Gestión completa de una orden.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/services.py` → `OrderService`, `ReturnService`

**Endpoints GET:**
- `GET /api/v1/marketplace/orders/{id}/`

**Endpoints POST/PUT:**
- `POST /api/v1/marketplace/orders/{id}/prepare/`
- `POST /api/v1/marketplace/orders/{id}/ship/`
- `POST /api/v1/marketplace/orders/{id}/deliver/`
- `POST /api/v1/marketplace/orders/{id}/return/approve/`
- `POST /api/v1/marketplace/orders/{id}/return/reject/`

**Componentes:**
- Información del cliente
- Items de la orden
- Estado con timeline
- Información de envío
- Pagos asociados
- Solicitud de devolución (si existe)
- Acciones según estado

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Iniciar Preparación" | POST | Cambiar a PREPARING |
| "Marcar Enviado" | Abrir modal | Modal con tracking |
| "Confirmar Entrega" | POST | Cambiar a DELIVERED |
| "Aprobar Devolución" | POST | Procesar devolución |
| "Rechazar Devolución" | POST | Rechazar |

**Popups/Modals:**
- Modal de ingreso de tracking number
- Modal de confirmación de devolución

---

### SCREEN-053: Gestión de Inventario

**Ruta Frontend:** `/admin/inventory`

**Descripción:** Control de stock de productos.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/models.py` → `ProductVariant`, `InventoryMovement`

**Endpoints GET:**
- `GET /api/v1/marketplace/variants/`
- `GET /api/v1/marketplace/inventory/movements/`

**Endpoints POST:**
- `POST /api/v1/marketplace/inventory/adjust/`

**Componentes:**
- Tabla de variantes:
  - Producto
  - Variante
  - SKU
  - Stock actual
  - Reservado
  - Disponible
  - Umbral bajo
- Alertas de stock bajo
- Historial de movimientos
- Ajuste manual de stock

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Ajustar Stock" | Abrir modal | Modal ajuste |
| "Ver Movimientos" | Navegar | `/admin/inventory/movements` |
| Fila producto | Navegar | `/admin/products/{id}` |

**Popups/Modals:**
- Modal de ajuste de stock (cantidad, motivo)

---

### SCREEN-054: Gestión de Productos

**Ruta Frontend:** `/admin/products`

**Descripción:** CRUD de productos del marketplace.

**Backend Files:**
- `marketplace/views.py`
- `marketplace/models.py` → `Product`, `ProductVariant`, `ProductImage`

**Endpoints GET/POST/PUT/DELETE:**
- `GET /api/v1/marketplace/products/`
- `POST /api/v1/marketplace/products/`
- `PUT /api/v1/marketplace/products/{id}/`
- `DELETE /api/v1/marketplace/products/{id}/`

**Componentes:**
- Lista de productos
- Botón "Nuevo Producto"
- Toggle activo/inactivo
- Acciones: editar, eliminar

**Botones y Acciones:**
| Botón | Acción | Destino |
|-------|--------|---------|
| "Nuevo Producto" | Navegar | `/admin/products/new` |
| "Editar" | Navegar | `/admin/products/{id}/edit` |
| Toggle activo | PUT | Cambiar estado |

---

### SCREEN-055: Editor de Producto

**Ruta Frontend:** `/admin/products/{id}/edit` o `/admin/products/new`

**Descripción:** Formulario de producto.

**Componentes:**
- Nombre
- Descripción
- Categoría
- Días de preparación
- Activo (toggle)
- Sección de imágenes (upload múltiple)
- Sección de variantes:
  - Nombre variante
  - SKU
  - Precio regular
  - Precio VIP
  - Stock inicial
  - Umbral stock bajo

---

### SCREEN-056: Gestión de Servicios

**Ruta Frontend:** `/admin/services`

**Descripción:** CRUD de servicios del spa.

**Backend Files:**
- `spa/views/`
- `spa/models/appointment.py` → `Service`, `ServiceCategory`

**Endpoints:**
- CRUD `/api/v1/services/`

**Componentes:**
- Lista de servicios por categoría
- Precio regular y VIP
- Duración
- Estado activo
- Soft delete

---

### SCREEN-057: Gestión de Disponibilidad

**Ruta Frontend:** `/admin/availability`

**Descripción:** Configurar horarios del staff.

**Backend Files:**
- `spa/models/appointment.py` → `StaffAvailability`, `AvailabilityExclusion`

**Endpoints:**
- CRUD `/api/v1/staff/{id}/availability/`
- CRUD `/api/v1/staff/{id}/exclusions/`

**Componentes:**
- Selector de staff
- Calendario semanal
- Bloques de disponibilidad
- Exclusiones (vacaciones, etc.)

---

### SCREEN-058: Logs de Conversaciones del Bot

**Ruta Frontend:** `/admin/bot/logs`

**Descripción:** Historial de conversaciones del bot.

**Backend Files:**
- `bot/models/conversation.py` → `BotConversationLog`

**Endpoints GET:**
- `GET /api/v1/bot/conversations/`

**Componentes:**
- Tabla de conversaciones:
  - Usuario/Anónimo
  - Mensaje
  - Respuesta (truncada)
  - Tokens usados
  - Latencia
  - Bloqueado (badge)
- Filtros: fecha, bloqueado, usuario
- Click para ver completo

---

### SCREEN-059: Panel de Notificaciones Admin

**Ruta Frontend:** `/admin/notifications`

**Descripción:** Notificaciones internas del sistema.

**Backend Files:**
- `core/models.py` → `AdminNotification`

**Endpoints GET:**
- `GET /api/v1/admin/notifications/`

**Endpoints PUT:**
- `PUT /api/v1/admin/notifications/{id}/read/`

**Componentes:**
- Lista de notificaciones:
  - Título
  - Tipo (badge de color)
  - Subtipo
  - Fecha
  - Leída/no leída
- Filtros por tipo
- Marcar como leída

---

## 2.2 PANTALLAS SOLO STAFF

---

### SCREEN-060: Mi Agenda (Staff)

**Ruta Frontend:** `/staff/my-schedule`

**Descripción:** Agenda personal del terapeuta.

**Backend Files:**
- `spa/views/appointments.py`

**Endpoints GET:**
- `GET /api/v1/appointments/?staff_member={me}`

**Componentes:**
- Vista de calendario personal
- Solo citas asignadas a este staff
- Próxima cita destacada
- Acciones rápidas

---

### SCREEN-061: Check-in de Cliente (Staff)

**Ruta Frontend:** `/staff/checkin`

**Descripción:** Buscar cliente y procesar llegada.

**Backend Files:**
- `spa/views/appointments.py`
- `profiles/views.py` → Kiosk

**Componentes:**
- Búsqueda por teléfono
- Citas del día de ese cliente
- Botón "Cliente Llegó"
- Botón "Iniciar Kiosk"
- Botón "Registrar Pago"

---

# 🔴 SECCIÓN 3: SOLO ADMIN

---

### SCREEN-062: Configuración Global

**Ruta Frontend:** `/admin/settings`

**Descripción:** GlobalSettings del sistema.

**Backend Files:**
- `core/models.py` → `GlobalSettings`
- `core/views.py` (si existe endpoint)

**Endpoints GET/PUT:**
- `GET /api/v1/settings/`
- `PUT /api/v1/settings/`

**Componentes:**
- Formulario con todos los settings:
  - Porcentaje de anticipo
  - Capacidad baja supervisión
  - Buffer entre citas
  - Precio VIP mensual
  - Minutos para cancelar sin pago
  - Días de vigencia de créditos
  - Ventana de devoluciones
  - Política de no-show
  - Configuración de lealtad
  - Quiet hours globales
  - Timezone
  - Configuración de lista de espera
  - Comisión desarrollador (solo lectura o incremento)
  - Umbral de pago desarrollador
- Validaciones inline
- Botón guardar

**Restricciones:**
- `developer_commission_percentage` solo puede mantenerse o incrementarse

---

### SCREEN-063: Logs de Auditoría

**Ruta Frontend:** `/admin/audit-logs`

**Descripción:** Historial de acciones auditadas.

**Backend Files:**
- `core/models.py` → `AuditLog`

**Endpoints GET:**
- `GET /api/v1/audit-logs/`

**Componentes:**
- Tabla con columnas:
  - Fecha/hora
  - Acción
  - Admin ejecutor
  - Usuario objetivo
  - Cita relacionada
  - Detalles
- Filtros por:
  - Acción
  - Admin
  - Usuario objetivo
  - Rango de fechas
- Exportar

---

### SCREEN-064: Dashboard Financiero

**Ruta Frontend:** `/admin/finances`

**Descripción:** Resumen financiero del negocio.

**Backend Files:**
- `analytics/services.py` → `KpiService`
- `finances/services.py` → `DeveloperCommissionService`
- `spa/models/payment.py`

**Endpoints GET:**
- `GET /api/v1/analytics/finances/`
- `GET /api/v1/finances/commissions/summary/`

**Componentes:**
- KPIs financieros:
  - Ingresos del período
  - Pagos pendientes
  - Deuda por recuperar
  - Créditos emitidos
- Gráfico de ingresos por período
- Desglose por tipo de pago
- Comisiones del desarrollador:
  - Deuda actual
  - Estado de mora
  - Última dispersión

---

### SCREEN-065: Gestión de Comisiones

**Ruta Frontend:** `/admin/finances/commissions`

**Descripción:** Detalle de comisiones del desarrollador.

**Backend Files:**
- `finances/models.py` → `CommissionLedger`
- `finances/services.py` → `DeveloperCommissionService`

**Endpoints GET:**
- `GET /api/v1/finances/commissions/`

**Componentes:**
- Resumen:
  - Deuda total
  - Estado mora (badge)
  - Desde cuándo en mora
- Lista de CommissionLedger:
  - Pago origen
  - Monto comisión
  - Monto pagado
  - Estado
  - Transfer ID Wompi
- Botón "Forzar Dispersión" (si hay deuda)

---

### SCREEN-066: Gestión de Paquetes

**Ruta Frontend:** `/admin/packages`

**Descripción:** CRUD de paquetes de servicios.

**Backend Files:**
- `spa/views/packages.py`
- `spa/models/voucher.py` → `Package`, `PackageService`

**Endpoints:**
- CRUD `/api/v1/packages/`

**Componentes:**
- Lista de paquetes
- Crear/editar paquete:
  - Nombre
  - Descripción
  - Precio
  - Servicios incluidos (multi-select con cantidad)
  - Meses VIP incluidos
  - Días de validez

---

### SCREEN-067: Gestión de Templates de Notificación

**Ruta Frontend:** `/admin/notification-templates`

**Descripción:** Editar plantillas de notificación.

**Backend Files:**
- `notifications/models.py` → `NotificationTemplate`

**Endpoints:**
- CRUD `/api/v1/notifications/templates/`

**Componentes:**
- Lista de templates por event_code
- Editor con:
  - Event code
  - Canal
  - Subject template
  - Body template
  - Variables disponibles (referencia)
  - Preview renderizado
  - Activo (toggle)
- Historial de versiones

---

### SCREEN-068: Gestión de Consentimientos

**Ruta Frontend:** `/admin/consent-templates`

**Descripción:** Versionar documentos legales.

**Backend Files:**
- `profiles/models.py` → `ConsentTemplate`
- `profiles/views.py`

**Endpoints:**
- CRUD `/api/v1/profiles/consent-templates/`

**Componentes:**
- Lista de versiones
- Crear nueva versión:
  - Título
  - Cuerpo (editor WYSIWYG)
  - Marcar como activa
- Al activar nueva, desactiva anterior
- Historial de versiones

---

### SCREEN-069: Dashboard de Analytics

**Ruta Frontend:** `/admin/analytics`

**Descripción:** KPIs completos del negocio.

**Backend Files:**
- `analytics/services.py` → `KpiService`
- `analytics/views.py`

**Endpoints GET:**
- `GET /api/v1/analytics/kpis/`
- `GET /api/v1/analytics/sales/`
- `GET /api/v1/analytics/debt/`

**Componentes:**
- Selectores de fecha
- Filtros por staff y categoría
- Cards de KPIs:
  - Tasa de conversión
  - Tasa de no-show
  - Tasa de reagendamiento
  - Utilización de staff
  - LTV por rol
  - Valor promedio de orden
- Gráficos:
  - Ingresos por período
  - Citas por estado
  - Servicios más populares
- Exportar reporte

---

### SCREEN-070: Configuración del Bot

**Ruta Frontend:** `/admin/bot/config`

**Descripción:** Configurar el asistente virtual.

**Backend Files:**
- `bot/models/config.py` → `BotConfiguration`

**Endpoints:**
- GET/PUT `/api/v1/bot/configuration/`

**Componentes:**
- Nombre del sitio
- URL de booking
- Teléfono admin
- Editor de System Prompt
- Precios de API (input/output por 1K tokens)
- Umbral de alerta de costo diario
- Umbral de tokens promedio
- Habilitar alertas críticas
- Configuración de auto-bloqueo
- Preview del prompt renderizado

---

### SCREEN-071: Seguridad - IPs Bloqueadas

**Ruta Frontend:** `/admin/security/blocked-ips`

**Descripción:** Gestionar IPs bloqueadas.

**Backend Files:**
- `bot/models/security.py` → `IPBlocklist`
- `users/views.py` → `BlockIPView`

**Endpoints:**
- `GET /api/v1/security/blocked-ips/`
- `POST /api/v1/security/block-ip/`
- `DELETE /api/v1/security/blocked-ips/{id}/`

**Componentes:**
- Lista de IPs bloqueadas:
  - IP
  - Razón
  - Fecha bloqueo
  - Expira
- Botón "Bloquear IP Manual"
- Botón desbloquear

**Popups/Modals:**
- Modal bloquear IP (IP, duración, razón)

---

### SCREEN-072: Seguridad - Actividad Sospechosa

**Ruta Frontend:** `/admin/security/suspicious`

**Descripción:** Monitoreo de actividad sospechosa.

**Backend Files:**
- `bot/models/security.py` → `SuspiciousActivity`
- `bot/suspicious_activity_detector/`

**Endpoints GET:**
- `GET /api/v1/security/suspicious-activity/`

**Componentes:**
- Lista de actividades:
  - IP
  - Tipo de actividad
  - Severidad
  - Timestamp
  - Detalles
- Filtros por severidad y tipo
- Acción rápida "Bloquear IP"
- Estadísticas de amenazas

---

### SCREEN-073: Gestión de Categorías de Servicio

**Ruta Frontend:** `/admin/categories`

**Descripción:** CRUD de categorías.

**Backend Files:**
- `spa/models/appointment.py` → `ServiceCategory`

**Endpoints:**
- CRUD `/api/v1/categories/`

**Componentes:**
- Lista de categorías
- Crear/editar:
  - Nombre
  - Descripción
  - Es baja supervisión (toggle)
- Soft delete

---

### SCREEN-074: Gestión de Staff

**Ruta Frontend:** `/admin/staff`

**Descripción:** Administrar personal del spa.

**Backend Files:**
- `users/models.py` → `CustomUser` (role=STAFF)
- `spa/models/appointment.py` → `StaffAvailability`

**Endpoints:**
- `GET /api/v1/users/?role=STAFF`
- `POST /api/v1/users/create-staff/`

**Componentes:**
- Lista de staff:
  - Nombre
  - Teléfono
  - Email
  - Estado
- Crear nuevo staff
- Editar disponibilidad
- Activar/desactivar

---

### SCREEN-075: Preguntas Dosha

**Ruta Frontend:** `/admin/dosha-questions`

**Descripción:** Gestionar cuestionario Dosha.

**Backend Files:**
- `profiles/views.py` → `DoshaQuestionViewSet`
- `profiles/models.py` → `DoshaQuestion`, `DoshaOption`

**Endpoints:**
- CRUD `/api/v1/profiles/dosha-questions/`

**Componentes:**
- Lista de preguntas por categoría
- Crear/editar pregunta:
  - Texto
  - Categoría
  - Opciones (con dosha asociado y peso)
- Ordenar preguntas

---

### SCREEN-076: Webhooks y Eventos

**Ruta Frontend:** `/admin/webhooks`

**Descripción:** Monitoreo de webhooks recibidos.

**Backend Files:**
- `spa/models/payment.py` → `WebhookEvent`

**Endpoints GET:**
- `GET /api/v1/webhooks/events/`

**Componentes:**
- Lista de eventos:
  - Tipo
  - Estado
  - Timestamp
  - Error (si falló)
- Filtros por estado y tipo
- Ver payload completo
- Reintentar evento fallido

---

### SCREEN-077: Reportes y Exportaciones

**Ruta Frontend:** `/admin/reports`

**Descripción:** Generación de reportes.

**Backend Files:**
- `analytics/views.py`
- `spa/views/reports.py`

**Endpoints:**
- `GET /api/v1/reports/generate/?type={type}&format={format}`

**Componentes:**
- Tipos de reporte:
  - Ingresos por período
  - Citas por estado
  - Servicios más vendidos
  - Clientes más frecuentes
  - Inventario valorizado
  - Comisiones del período
- Selector de formato (PDF, Excel, CSV)
- Selector de rango de fechas
- Generar y descargar

---

### SCREEN-078: Historial de Perfiles Clínicos

**Ruta Frontend:** `/admin/profiles/{id}/history`

**Descripción:** Ver versiones históricas de perfil.

**Backend Files:**
- `profiles/views.py` → `ClinicalProfileHistoryViewSet`

**Endpoints GET:**
- `GET /api/v1/profiles/history/?profile_id={id}`

**Componentes:**
- Timeline de cambios
- Cada versión:
  - Fecha/hora
  - Usuario que modificó
  - Campos cambiados (diff)
- Comparar versiones

---

### SCREEN-079: Ajustes Financieros

**Ruta Frontend:** `/admin/finances/adjustments`

**Descripción:** Historial y creación de ajustes.

**Backend Files:**
- `spa/models/payment.py` → `FinancialAdjustment`
- `spa/services/payments.py` → `FinancialAdjustmentService`

**Endpoints:**
- `GET /api/v1/finances/adjustments/`
- `POST /api/v1/finances/adjustments/`

**Componentes:**
- Lista de ajustes:
  - Usuario
  - Tipo (crédito/débito)
  - Monto
  - Razón
  - Creado por
  - Fecha
- Botón "Nuevo Ajuste"

**Popups/Modals:**
- Modal crear ajuste:
  - Buscar usuario
  - Tipo
  - Monto (máx $5,000,000)
  - Razón
  - Pago relacionado (opcional)

---

### SCREEN-080: Métricas del Bot

**Ruta Frontend:** `/admin/bot/metrics`

**Descripción:** Dashboard de uso del bot.

**Backend Files:**
- `bot/tasks/cost_monitor.py`
- `bot/models/conversation.py`

**Endpoints GET:**
- `GET /api/v1/bot/metrics/`

**Componentes:**
- Métricas del día:
  - Total conversaciones
  - Tokens usados
  - Costo estimado USD
  - Promedio tokens/conversación
  - Tasa de bloqueos
- Gráficos de tendencia
- Alertas activas
- Top usuarios por uso

---

## 📊 RESUMEN ESTADÍSTICO

| Sección | Cantidad de Pantallas |
|---------|----------------------|
| Usuario Anónimo/No Verificado | 13 |
| Usuario Registrado (CLIENT/VIP) | 28 |
| Staff y Admin (Compartidas) | 18 |
| Solo Admin | 21 |
| **TOTAL** | **80 pantallas** |

---

## 🔗 MAPA DE DEPENDENCIAS DE ENDPOINTS

```
users/
├── urls.py → 25 endpoints
│   ├── register, verify-sms, token, token/refresh
│   ├── password-reset/*, change-password
│   ├── me, sessions/*, logout, logout-all
│   ├── totp/setup, totp/verify
│   └── flag-non-grata, export, block-ip

profiles/
├── urls.py → 15 endpoints
│   ├── clinical-profiles/*, dosha-questions/*
│   ├── dosha-quiz/submit, consent-templates/*
│   ├── consents/sign, export
│   └── kiosk/* (start, status, heartbeat, lock)

spa/
├── urls.py → 30 endpoints
│   ├── services/*, categories/*
│   ├── appointments/*, availability
│   ├── packages/*, vouchers/*
│   ├── payments/*, credits/*
│   ├── waitlist/*
│   └── staff/availability/*

marketplace/
├── urls.py → 20 endpoints
│   ├── products/*, variants/*
│   ├── cart/*, orders/*
│   ├── inventory/*, movements
│   └── returns/*

notifications/
├── urls.py → 8 endpoints
│   ├── preferences/*, templates/*
│   └── logs/*

bot/
├── urls.py → 12 endpoints
│   ├── webhook, chat
│   ├── handoffs/*, messages/*
│   ├── configuration
│   └── metrics

analytics/
├── urls.py → 6 endpoints
│   ├── kpis/, finances/
│   └── reports/*

finances/
├── urls.py → 5 endpoints
│   └── commissions/*, webhooks/*

core/
├── (endpoints admin)
│   ├── settings/, audit-logs/
│   └── admin-notifications/*
```

---

*Documento generado para planificación de desarrollo frontend*
*Total: 80 pantallas únicas, ~120+ endpoints backend*
