# 🚀 Roadmap de Implementación Frontend - StudioZens (Revisado)

Este plan estructura el trabajo para que no te adelantes innecesariamente. Primero los cimientos técnicos, luego la selección visual, y finalmente la construcción.

## 📅 Estrategia General
*   **Fase 1: Cimientos Técnicos (El "Lienzo en Blanco")**.
*   **Fase 2: Identidad y Selección de Activos (El "Shopping")**.
*   **Fase 3: Integración de UI**.
*   **Fase 4: Funcionalidad Core (Reservas)**.
*   **Fase 5: Expansión (Admin, Tienda)**.

---

## 🛠 Fase 1: Cimientos Técnicos (Días 1-2)
*Objetivo: Tener un entorno de desarrollo profesional listo para recibir cualquier diseño.*
*No necesitas saber qué plantilla usarás todavía.*

1.  **Inicialización del Repositorio**:
    *   `npx create-next-app@latest studiozens-frontend` (TypeScript, Tailwind, ESLint).
    *   Configurar estructura de carpetas limpia (`/components`, `/lib`, `/services`, `/hooks`).
2.  **Configuración de Herramientas Base**:
    *   Instalar **Axios/Ky** (para conectar con tu backend Django).
    *   Instalar **TanStack Query** (React Query) -> *Indispensable para manejar datos asíncronos.*
    *   Instalar **Zustand** -> *Para el estado global (carrito, usuario).*
    *   Configurar variables de entorno (`.env.local`) apuntando a tu API local.
3.  **Sistema de Rutas (Skeleton)**:
    *   Crea las carpetas de las rutas principales vacías: `/book`, `/dashboard`, `/admin`.
    *   Esto te permite probar navegación aunque las páginas estén en blanco.

---

## 🎨 Fase 2: Identidad y Selección de Activos (Días 3-5)
*Objetivo: Definir CÓMO se verá. Aquí es donde buscas y compras.*
*Ahora que tienes el código base, puedes buscar con calma sabiendo qué necesitas.*

1.  **Definición de Estilo (Moodboard)**:
    *   Define tu paleta de colores primaria (ej. ¿Dorado y Negro? ¿Pasteles y Blanco?).
    *   Define tu tipografía (Google Fonts).
2.  **Selección de Iconografía**:
    *   Decide qué set usarás. Recomendación: **Lucide React** (muy limpio, estándar en Next.js) o **Phosphor Icons**. Instala el paquete elegido.
3.  **Búsqueda y Compra de Plantillas**:
    *   **Ahora sí, busca la plantilla.**
    *   *Criterio*: Busca una que se acerque a tu paleta de colores o que sea fácil de cambiar.
    *   Compra/Descarga la plantilla **Pública** (Landing/Spa).
    *   Compra/Descarga la plantilla **Admin** (Dashboard).
4.  **Banco de Imágenes**:
    *   Recopila las imágenes de "Placeholder" de alta calidad (Unsplash/Pexels) para Servicios, Productos y Hero.
    *   Guárdalas en `/public/images/placeholders`.

---

## 🏗 Fase 3: Integración de UI (Días 6-8)
*Objetivo: Fusionar las plantillas compradas con tu proyecto base.*

1.  **Extracción de Componentes (Atomic Design)**:
    *   Abre el código de la plantilla comprada.
    *   Copia sus componentes base a tu proyecto: `Button`, `Card`, `Input`, `Badge`.
    *   Adapta los colores de Tailwind (`tailwind.config.ts`) para que coincidan con tu marca.
2.  **Layouts Maestros**:
    *   Crea `app/(public)/layout.tsx`: Header y Footer públicos.
    *   Crea `app/(admin)/layout.tsx`: Sidebar y Navbar del admin.
3.  **Landing Page Inicial**:
    *   Monta la página de inicio usando los componentes que extrajiste.

---

## 📅 Fase 4: Motor de Reservas (Core) (Días 9-14)
*Objetivo: Que el sistema funcione.*

1.  **Catálogo Real**:
    *   Conecta las "Service Cards" con tu API de Django.
2.  **Flujo de Agendamiento**:
    *   Paso 1: Selección de Servicios (State management).
    *   Paso 2: **Calendario**. Aquí decides si usas el calendario de la plantilla Admin o instalas `FullCalendar`.
    *   Paso 3: Resumen y Pago.

---

## 👮 Fase 5: Gestión y Admin (Días 15-18)
*Objetivo: Control del negocio.*

1.  **Tablas de Datos**:
    *   Trae el componente "Data Table" de tu plantilla Admin.
    *   Conéctalo al endpoint de Citas y Usuarios.
2.  **Dashboard**:
    *   Implementa los gráficos/stats.

---

## 🛍 Fase 6: E-commerce y Extras (Días 19+)
*Objetivo: Venta de productos.*

1.  **Tienda**:
    *   Implementa el Grid de Productos y Carrito.
2.  **Detalles Finales**:
    *   Chat Widget.
    *   Modo Kiosk.

---

### 💡 ¿Por qué este orden?
1.  **Fase 1** te permite programar lógica (conexión API, autenticación) sin distraerte con "qué color es el botón".
2.  **Fase 2** te da un tiempo dedicado solo a "Shopping" y diseño, sin sentirte culpable por no programar.
3.  **Fase 3** es donde todo se une.

### 🏁 Tu Siguiente Paso
Olvídate de las plantillas por hoy. **Ejecuta la Fase 1**. Crea el proyecto, instala las librerías y configura la estructura. Cuando termines eso, tendrás la mente más clara para elegir el diseño en la Fase 2.
