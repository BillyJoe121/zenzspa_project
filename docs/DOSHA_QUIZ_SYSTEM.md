# Sistema de Quiz de Doshas - Studio Zens

## 📋 Resumen del Sistema

El sistema de quiz de doshas permite determinar el **dosha dominante** (Vata, Pitta o Kapha) de cada usuario mediante un cuestionario basado en la medicina Ayurvédica.

---

## 🏗️ Arquitectura del Sistema

### **Modelos de Base de Datos**

#### 1. **DoshaQuestion** - Preguntas del Quiz
```python
class DoshaQuestion(BaseModel):
    text = TextField(unique=True)           # Texto de la pregunta
    order = IntegerField(default=0)         # Orden de aparición
    is_active = BooleanField(default=True)  # Si está activa
    category = CharField(max_length=50)     # Categoría (Físico, Mental, Emocional, etc.)
```

**Campos:**
- `text`: La pregunta (ej: "¿Cómo es tu constitución física?")
- `order`: Orden en que aparece en el quiz (0, 1, 2, ...)
- `is_active`: Si la pregunta está activa (permite desactivar sin borrar)
- `category`: Categoría para agrupar preguntas (ej: "Físico", "Mental", "Digestivo")

#### 2. **DoshaOption** - Opciones de Respuesta
```python
class DoshaOption(BaseModel):
    question = ForeignKey(DoshaQuestion)        # Pregunta a la que pertenece
    text = CharField(max_length=255)            # Texto de la opción
    associated_dosha = CharField(choices=Dosha) # VATA, PITTA, KAPHA
    weight = PositiveIntegerField(default=1)    # Peso/puntuación
```

**Campos:**
- `question`: Relación con la pregunta
- `text`: Descripción de la opción (ej: "Delgado, huesos prominentes")
- `associated_dosha`: Dosha al que corresponde (VATA, PITTA o KAPHA)
- `weight`: Puntuación que suma al dosha (normalmente 1, pero puede ser mayor para preguntas más importantes)

**Constraint**: Cada pregunta debe tener **exactamente 3 opciones** (una para cada dosha)

#### 3. **ClientDoshaAnswer** - Respuestas del Usuario
```python
class ClientDoshaAnswer(BaseModel):
    profile = ForeignKey(ClinicalProfile)      # Perfil del usuario
    question = ForeignKey(DoshaQuestion)       # Pregunta respondida
    selected_option = ForeignKey(DoshaOption)  # Opción seleccionada

    # Constraint: Un usuario solo puede responder una vez cada pregunta
    unique_together = ('profile', 'question')
```

#### 4. **ClinicalProfile** - Almacena el Dosha Calculado
```python
class ClinicalProfile(BaseModel):
    user = OneToOneField(CustomUser)
    dosha = CharField(choices=Dosha)  # VATA, PITTA, KAPHA, UNKNOWN
    # ... otros campos ...
```

**Método de cálculo**:
```python
def calculate_dominant_dosha(self):
    """
    Suma los pesos de las opciones seleccionadas por dosha
    y asigna el dosha con mayor puntuación.
    """
```

---

## 🎯 Tipos de Doshas

```python
class Dosha(models.TextChoices):
    VATA = 'VATA', 'Vata'      # Aire + Éter
    PITTA = 'PITTA', 'Pitta'   # Fuego + Agua
    KAPHA = 'KAPHA', 'Kapha'   # Tierra + Agua
    UNKNOWN = 'UNKNOWN', 'Desconocido'
```

### **Características Generales**

| Dosha | Elementos | Características |
|-------|-----------|-----------------|
| **Vata** | Aire + Éter | Delgado, energético, creativo, irregular, frío |
| **Pitta** | Fuego + Agua | Atlético, intenso, determinado, caliente, competitivo |
| **Kapha** | Tierra + Agua | Robusto, calmado, estable, fresco, compasivo |

---

## 📐 Estructura de las Preguntas

### **Formato Estándar**

Cada pregunta debe tener:
1. **Texto claro y conciso**
2. **Categoría** (para agrupar preguntas relacionadas)
3. **Orden** (para controlar la secuencia)
4. **3 opciones exactamente** (una para cada dosha)

### **Categorías Recomendadas**

```
1. Físico         - Constitución, peso, piel, cabello
2. Digestivo      - Apetito, digestión, eliminación
3. Mental         - Forma de pensar, memoria, aprendizaje
4. Emocional      - Reacciones emocionales, estrés
5. Energía        - Niveles de energía, sueño, actividad
6. Temperatura    - Sensibilidad al frío/calor
7. Comportamiento - Hábitos, patrones de conducta
```

### **Ejemplo de Pregunta Bien Estructurada**

```json
{
  "text": "¿Cómo es tu constitución física?",
  "category": "Físico",
  "order": 1,
  "is_active": true,
  "options": [
    {
      "text": "Delgado, huesos prominentes, difícil ganar peso",
      "associated_dosha": "VATA",
      "weight": 1
    },
    {
      "text": "Atlético, musculoso, peso moderado",
      "associated_dosha": "PITTA",
      "weight": 1
    },
    {
      "text": "Robusto, tendencia a ganar peso fácilmente",
      "associated_dosha": "KAPHA",
      "weight": 1
    }
  ]
}
```

---

## 🔢 Sistema de Pesos

### **¿Cómo Funciona?**

1. El usuario responde cada pregunta seleccionando **una opción**
2. Cada opción tiene un `weight` (normalmente 1)
3. El sistema suma los pesos por dosha:
   ```
   VATA:  suma de weights de todas las opciones VATA seleccionadas
   PITTA: suma de weights de todas las opciones PITTA seleccionadas
   KAPHA: suma de weights de todas las opciones KAPHA seleccionadas
   ```
4. El dosha con **mayor puntuación** es el dominante

### **Ejemplo de Cálculo**

```
Usuario responde 10 preguntas:
- 6 opciones VATA (weight=1 cada una)  → VATA = 6
- 3 opciones PITTA (weight=1 cada una) → PITTA = 3
- 1 opción KAPHA (weight=1)            → KAPHA = 1

Resultado: Dosha dominante = VATA (6 puntos)
```

### **Pesos Variables (Opcional)**

Puedes usar pesos diferentes para dar más importancia a ciertas preguntas:

```json
{
  "text": "¿Cómo reaccionas bajo estrés? (Pregunta clave)",
  "options": [
    {
      "text": "Me siento ansioso y disperso",
      "associated_dosha": "VATA",
      "weight": 2  // ← Peso doble
    },
    {
      "text": "Me irrito y me vuelvo crítico",
      "associated_dosha": "PITTA",
      "weight": 2
    },
    {
      "text": "Me retiro y me vuelvo apático",
      "associated_dosha": "KAPHA",
      "weight": 2
    }
  ]
}
```

**Recomendación**: Mantener `weight=1` para todas las opciones a menos que haya preguntas específicamente más importantes.

---

## 📊 Cantidad de Preguntas Recomendada

### **Mínimo Viable**
- **10-12 preguntas** - Quiz básico, rápido (5-7 minutos)

### **Recomendado**
- **20-25 preguntas** - Quiz completo, buena precisión (10-15 minutos)

### **Exhaustivo**
- **30-40 preguntas** - Quiz detallado, máxima precisión (15-20 minutos)

**Para Studio Zens**: Recomiendo **20-25 preguntas** divididas así:
- Físico: 5-6 preguntas
- Digestivo: 3-4 preguntas
- Mental/Emocional: 5-6 preguntas
- Energía/Sueño: 3-4 preguntas
- Comportamiento: 3-4 preguntas

---

## 🔌 Endpoints del API

### **1. Obtener Preguntas del Quiz**

**Endpoint**: `GET /api/v1/dosha-quiz/`

**Autenticación**: Requerida

**Respuesta**:
```json
[
  {
    "id": "uuid-pregunta-1",
    "text": "¿Cómo es tu constitución física?",
    "category": "Físico",
    "order": 1,
    "options": [
      {
        "id": "uuid-opcion-1",
        "text": "Delgado, huesos prominentes",
        "associated_dosha": "VATA",
        "weight": 1
      },
      {
        "id": "uuid-opcion-2",
        "text": "Atlético, musculoso",
        "associated_dosha": "PITTA",
        "weight": 1
      },
      {
        "id": "uuid-opcion-3",
        "text": "Robusto, tendencia a ganar peso",
        "associated_dosha": "KAPHA",
        "weight": 1
      }
    ]
  }
]
```

**Notas**:
- Solo retorna preguntas con `is_active=True`
- Ordenadas por `order` ascendente
- Incluye todas las opciones de cada pregunta

### **2. Enviar Respuestas del Quiz**

**Endpoint**: `POST /api/v1/dosha-quiz/submit/`

**Autenticación**: Requerida

**Body**:
```json
{
  "answers": [
    {
      "question_id": "uuid-pregunta-1",
      "selected_option_id": "uuid-opcion-vata"
    },
    {
      "question_id": "uuid-pregunta-2",
      "selected_option_id": "uuid-opcion-pitta"
    }
  ]
}
```

**Respuesta Exitosa (200 OK)**:
```json
{
  "dosha": "VATA",
  "message": "Cuestionario guardado y Dosha calculado exitosamente."
}
```

**Validaciones**:
- El usuario debe tener un `ClinicalProfile`
- No se permiten respuestas duplicadas para la misma pregunta
- Las opciones deben pertenecer a la pregunta indicada

**Comportamiento**:
1. Elimina las respuestas anteriores del usuario
2. Guarda las nuevas respuestas
3. Calcula el dosha dominante automáticamente
4. Actualiza el campo `dosha` en `ClinicalProfile`

---

## 🛠️ Administración desde el Frontend (Admin)

### **Panel de Django Admin**

Acceso: `/admin/profiles/doshaquestion/`

**Funcionalidades**:

1. **Crear nueva pregunta**:
   - Agregar texto
   - Seleccionar categoría
   - Definir orden
   - Marcar como activa

2. **Agregar opciones inline**:
   - Se muestran 3 campos para las 3 opciones
   - Cada opción tiene: texto, dosha asociado, peso

3. **Editar preguntas existentes**:
   - Cambiar texto
   - Reordenar (cambiar `order`)
   - Desactivar/activar (`is_active`)
   - Modificar opciones

4. **Filtrar y buscar**:
   - Por categoría
   - Por texto de la pregunta

5. **Ver respuestas de clientes**:
   - Panel separado: `/admin/profiles/clientdoshaanswer/`
   - Ver qué usuarios respondieron qué

---

## 📝 Plantilla para Crear Preguntas

### **Template JSON para Importar**

```json
[
  {
    "text": "TEXTO DE LA PREGUNTA AQUÍ",
    "category": "CATEGORÍA",
    "order": NÚMERO,
    "is_active": true,
    "options": [
      {
        "text": "Descripción característica de VATA",
        "associated_dosha": "VATA",
        "weight": 1
      },
      {
        "text": "Descripción característica de PITTA",
        "associated_dosha": "PITTA",
        "weight": 1
      },
      {
        "text": "Descripción característica de KAPHA",
        "associated_dosha": "KAPHA",
        "weight": 1
      }
    ]
  }
]
```

### **Script de Importación**

Puedo crear un comando Django para importar preguntas desde un archivo JSON:
```bash
python manage.py import_dosha_questions preguntas.json
```

---

## 🔄 Flujo Completo del Usuario

```
1. Usuario inicia sesión
   ↓
2. Frontend consulta: GET /api/v1/dosha-quiz/
   ↓
3. Muestra preguntas una por una (o todas juntas)
   ↓
4. Usuario selecciona opciones
   ↓
5. Frontend envía: POST /api/v1/dosha-quiz/submit/
   ↓
6. Backend calcula dosha dominante
   ↓
7. Backend actualiza ClinicalProfile.dosha
   ↓
8. Frontend muestra resultado
```

---

## 📌 Consideraciones Importantes

### **1. Unicidad de Respuestas**
- Un usuario solo puede responder **una vez por pregunta**
- Si reenvía el quiz, se **borran las respuestas anteriores** y se calculan las nuevas

### **2. Cálculo Automático**
- El dosha se calcula automáticamente al enviar las respuestas
- También se puede recalcular manualmente llamando a:
  ```python
  profile.calculate_dominant_dosha()
  ```

### **3. Preguntas Inactivas**
- Las preguntas con `is_active=False` **no aparecen** en el quiz
- Las respuestas anteriores a esas preguntas **se mantienen** en la BD

### **4. Edición de Opciones**
- Si cambias el peso o dosha de una opción, debes recalcular el dosha de usuarios que ya respondieron
- Recomendación: **No modificar** preguntas/opciones después de lanzar el quiz en producción

---

## 🧪 Testing

### **Tests Existentes**
- ✅ Cálculo de dosha con respuestas variadas
- ✅ Envío de quiz completo
- ✅ Validación de respuestas duplicadas
- ✅ Manejo de usuario sin ClinicalProfile
- ✅ Recalculo cuando se borran respuestas

### **Tests Recomendados Adicionales**
- Verificar orden correcto de preguntas
- Validar que todas las preguntas activas tengan 3 opciones
- Probar pesos variables

---

## 📚 Recursos Ayurvédicos

Para diseñar las preguntas, considera estas áreas clave:

### **Características Físicas**
- Constitución corporal
- Piel (seca/grasa/mixta)
- Cabello (fino/grueso/moderado)
- Peso (difícil ganar/moderado/fácil ganar)

### **Digestión**
- Apetito (irregular/fuerte/lento)
- Digestión (rápida/moderada/lenta)
- Preferencias alimentarias

### **Energía**
- Niveles de energía (variable/constante/estable)
- Sueño (ligero/moderado/profundo)
- Actividad física preferida

### **Mente y Emociones**
- Aprendizaje (rápido pero olvida/enfocado/lento pero retiene)
- Estrés (ansiedad/irritabilidad/retiro)
- Toma de decisiones (rápida/analítica/cautelosa)

### **Temperatura**
- Sensibilidad al frío/calor
- Manos y pies (fríos/calientes/templados)

---

## ✅ Checklist para Diseñar el Quiz

- [ ] Definir número total de preguntas (recomendado: 20-25)
- [ ] Dividir preguntas por categorías
- [ ] Redactar cada pregunta de forma clara
- [ ] Crear 3 opciones por pregunta (una por dosha)
- [ ] Asignar peso a cada opción (normalmente 1)
- [ ] Definir orden de las preguntas
- [ ] Validar que las descripciones sean mutuamente excluyentes
- [ ] Probar el quiz con casos conocidos
- [ ] Importar preguntas a la BD
- [ ] Verificar en admin que todo se vea correcto

---

## 🚀 Próximos Pasos

1. **Proporcionarme las preguntas** con el siguiente formato:
   ```
   Pregunta 1 (Categoría: Físico)
   - Opción VATA: Descripción
   - Opción PITTA: Descripción
   - Opción KAPHA: Descripción
   ```

2. **Crearé el comando de importación** para cargar las preguntas

3. **Ejecutaremos el seed** para poblar la BD

4. **Verificaremos** que todo funcione correctamente

---

¿Estás listo para proporcionarme las preguntas del quiz?
