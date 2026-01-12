# 🧪 Pruebas E2E - Marketplace

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

## MKT-001: Ver Catálogo de Productos (Happy Path)
```
➡️ Navegar a /shop (público o autenticado)
✅ Verificar productos activos mostrados
✅ Verificar imagen, nombre, precio
✅ Verificar variantes disponibles
✅ Verificar stock mostrado o "Agotado"
✅ Verificar productos inactivos NO mostrados
```

## MKT-002: Ver Detalle de Producto (Happy Path)
```
➡️ Navegar a /shop/[product-id]
✅ Verificar galería de imágenes
✅ Verificar descripción completa
✅ Verificar variantes con precios
✅ Verificar selector de cantidad
✅ Verificar precio VIP si usuario es VIP
```

## MKT-003: Agregar al Carrito (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /shop/[product-id]
📱 Seleccionar variante
📱 Seleccionar cantidad: 2
➡️ Click en "Agregar al Carrito"
✅ Verificar mensaje "Agregado al carrito"
✅ Verificar badge de carrito actualizado
💾 Verificar CartItem creado
```

## MKT-004: Agregar al Carrito - Sin Stock (Sad Path)
```
➡️ Login como CLIENT
➡️ Producto con stock=0
➡️ Click en "Agregar al Carrito"
✅ Verificar error "Producto agotado"
✅ Verificar botón deshabilitado
```

## MKT-005: Agregar al Carrito - Excede Stock (Sad Path)
```
➡️ Login como CLIENT
➡️ Producto con stock=3
📱 Seleccionar cantidad: 5
➡️ Click en "Agregar al Carrito"
✅ Verificar error "Solo hay 3 unidades disponibles"
```

## MKT-006: Ver Carrito (Happy Path)
```
➡️ Login como CLIENT con items en carrito
➡️ Navegar a /cart
✅ Verificar lista de items
✅ Verificar precio unitario y subtotal
✅ Verificar cantidad editable
✅ Verificar botón eliminar
✅ Verificar total del carrito
```

## MKT-007: Modificar Cantidad en Carrito (Happy Path)
```
➡️ En /cart
📱 Cambiar cantidad de 2 a 3
✅ Verificar subtotal actualizado
✅ Verificar total actualizado
💾 Verificar CartItem.quantity actualizado
```

## MKT-008: Eliminar Item del Carrito (Happy Path)
```
➡️ En /cart
➡️ Click en "Eliminar" en item
✅ Verificar item removido de lista
✅ Verificar total actualizado
💾 Verificar CartItem eliminado
```
