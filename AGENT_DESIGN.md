# Diseño del Sistema Multiagente para Borradores de Cómics (a partir de documentos)

## 1. Objetivo del sistema

Construir una aplicación que, a partir de documentos (guión profesional, fichas de personajes, fichas de escenarios, referencias visuales, notas y reglas de estilo), genere un **borrador de cómic**:

- Paneles (viñetas) con imágenes coherentes y consistentes.
- Diálogos y globos editables.
- Una vista “orgánica” por página para que el guionista/autor pueda leer el cómic como una pieza continua.
- Capacidad de **editar cada panel** con su propio prompt y versiones (regenerar, corregir zonas específicas, ampliar imagen, etc.).

Este diseño prioriza dos cosas:
1) **Consistencia** (personajes y escenarios se mantienen reconocibles).
2) **Personalización** (cada panel puede ajustarse sin romper el resto).

---

## 2. Conceptos clave (explicados en simple)

### 2.1. “Base de conocimiento” de personajes y escenarios
Se guarda la información de dos formas:

1) **Store Estructurado (Canonical Store)**
   - Es la “verdad oficial” del proyecto.
   - Guarda datos claros y específicos como:
     - Rasgos fijos del personaje (cabello, cicatriz, ropa base, paleta de colores).
     - Reglas del estilo (tipo de línea, sombreado, nivel de realismo, paleta).
     - Estado de continuidad (si alguien está herido, qué objeto tiene en mano, hora del día, clima).
   - Se usa para evitar que el modelo “se invente” cambios.

2) **Store de búsqueda (Vector Store)**
   - Sirve para encontrar rápidamente lo relevante entre muchos documentos.
   - Ejemplos:
     - “Busca notas sobre cómo es la ciudad de noche”
     - “Recupera referencias del personaje X enojado”
   - Ojo: esto ayuda a encontrar información, pero **no es la verdad oficial**. Si algo contradice el Canonical Store, se trata como conflicto.

---

## 3. Entradas del sistema

### 3.1. Documentos (Docs)
- Guión profesional (PDF u otro formato)
- Documento de estilo (tono artístico, referencias, reglas)
- Simbologías (convenciones: onomatopeyas, signos, recursos visuales)
- Trama / reseña / sinopsis
- Referencias de la vida real / inspiración (imágenes o texto)
- Notas adicionales (restricciones y preferencias del autor/editor)

### 3.2. Layout (estructura de páginas)
- Cantidad de páginas
- Cantidad de viñetas por página
- Tamaños y posiciones de viñetas
- Orden de lectura
- (Opcional) sugerencias de ritmo: “panel grande para impacto”, “panel pequeño para transición”, etc.

### 3.3. Fichas y referencias por entidad
Para cada personaje y escenario:
- Ficha (PDF) con descripción
- Imágenes de referencia (bocetos, fotos, arte previo)
- Datos estructurados (si existen): edad, ropa, rasgos clave, props, etc.

---

## 4. Salidas del sistema

1) **Paneles (viñetas) por separado**
- Cada panel se guarda como una imagen y tiene:
  - su prompt
  - sus referencias usadas
  - su historial de versiones

2) **Página “orgánica” (vista de lectura)**
- No es la “verdad rígida” del layout, sino una vista cómoda para leer y revisar.
- Se compone colocando paneles y globos sobre una página.
- Importante: esta página se arma de forma controlada (no se “pinta” toda con IA). Así se mantiene editable.

3) **Globos y textos editables**
- Los globos se guardan como objetos editables (texto y forma) y se pueden mover y redimensionar.

4) **Exportaciones**
- PDF por páginas
- Imágenes por página / por panel
- CBZ (formato común de cómics) si se requiere

---

## 5. Roles del sistema multiagente (qué hace cada uno)

La idea “multiagente” aquí no es “muchos agentes hablando sin control”, sino varios módulos con responsabilidades claras.

### A) Agente de Ingesta y Clasificación (Document Ingest)
**Qué hace**
- Recibe archivos y notas del usuario.
- Identifica el tipo de documento (guión, ficha de personaje, ficha de escenario, estilo, etc.).
- Extrae texto e imágenes y los deja listos para uso.

**Por qué**
- Los archivos vienen mezclados y en diferentes formatos. Necesitamos ordenarlos y limpiarlos.

---

### B) Agente de Construcción del Canon (Canonical Builder)
**Qué hace**
- Construye o actualiza el Canonical Store con:
  - Rasgos fijos por personaje (lo que no debe cambiar).
  - Rasgos fijos por escenario (lo que define el lugar).
  - Reglas de estilo del cómic.
  - “Restricciones” importantes del autor/editor.

**Por qué**
- La consistencia NO se logra solo “buscando en documentos”.
- Se logra manteniendo una “fuente de verdad” que el sistema respeta siempre.

---

### C) Agente de Planificación del Cómic (Planner)
**Qué hace**
- Toma el guión y crea una propuesta de:
  - Páginas y paneles (siguiendo el Layout o proponiendo uno si falta).
  - Qué ocurre en cada panel (acción, emoción, transición).
- Produce un “plan por panel” (Panel Spec), por ejemplo:
  - Qué personajes aparecen
  - Dónde están
  - Qué hacen
  - Qué debe verse en el fondo
  - Qué emoción debe percibirse

**Por qué**
- El guión suele describir de forma humana.
- Para generar imágenes, necesitamos una descripción más clara y estructurada por panel.

---

### D) Agente de Diálogos (Dialogue Structurer)
**Qué hace**
- NO reescribe el guión por defecto.
- Extrae y estructura:
  - quién habla
  - texto exacto
  - tipo (diálogo, narración, pensamiento, SFX)
  - emoción/énfasis (si el guión lo indica)
- (Opcional) puede sugerir versiones más cortas para que quepan en globos.

**Por qué**
- Si reescribes diálogos sin control, pierdes intención.
- Pero sí necesitas “ordenarlos” para ponerlos en globos y que se lean bien.

---

### E) Agente de Selección de Referencias (Reference Selector)
**Qué hace**
- Para cada panel, decide qué referencias usar como “guía visual”.
- No es una elección binaria (personaje o escenario), sino un paquete:
  - referencias del personaje (cara, ropa, expresiones)
  - referencias del escenario (arquitectura, ambiente)
  - estilo (referencias artísticas)
  - (opcional) referencia de pose

**Por qué**
- La consistencia sale de reusar buenas referencias de forma inteligente.
- Si mezclas referencias sin control, obtienes resultados incoherentes.

---

### F) Agente de Construcción de Prompt (Prompt Builder)
**Qué hace**
- Construye el prompt final del panel usando:
  - reglas globales de estilo
  - rasgos fijos de personaje/escenario (del Canonical Store)
  - lo específico del panel (acción, encuadre, emoción)
  - restricciones (“no cambies X”, “no uses Y”)
- Mantiene prompts ordenados por secciones para que sean editables.

**Por qué**
- Un prompt “gigante y desordenado” hace difícil iterar.
- Este módulo hace que cada panel sea personalizable sin romper el estilo general.

---

### G) Agente Generador/Editor de Imágenes (Image Generator + Editor)
**Qué hace**
- Genera la imagen del panel (primera versión).
- Permite:
  - regenerar variantes
  - editar una zona (por ejemplo, corregir una cara) sin rehacer todo
  - ampliar la imagen si el usuario cambia el recorte

**Por qué**
- En cómic se itera mucho.
- Necesitas edición localizada para no perder lo que ya está bien.

---

### H) Agente de Continuidad (Continuity Supervisor)
**Qué hace**
- Antes de generar un panel: revisa el estado actual (ropa, heridas, props, clima, etc.)
- Después de generar: confirma si el panel respeta continuidad.
- Si detecta cambios indeseados (ej. cambia peinado, cicatriz desaparece):
  - propone corrección (regenerar o editar zona)
  - actualiza el estado para el siguiente panel

**Por qué**
- La continuidad no sale “gratis”.
- Un cómic profesional requiere memoria de lo que pasó en paneles anteriores.

---

### I) Control de Calidad (Quality Gate)
**Qué hace**
- Revisa cada panel con reglas simples:
  - ¿se reconoce el personaje?
  - ¿el estilo se mantiene?
  - ¿hay espacio para globos?
  - ¿hay errores obvios (manos raras, caras deformes, etc.)?
- Si falla:
  - sugiere reintento con ajustes
  - o recomienda edición localizada

**Por qué**
- Sin un filtro de calidad, el sistema entrega paneles inconsistentes y el usuario se frustra.

---

### J) Compositor de Página (Page Composer)
**Qué hace**
- Crea la página “orgánica” juntando:
  - paneles ya generados
  - marcos, gutters, orden de lectura
  - globos de texto editables
- Genera una vista completa para lectura y revisión.

**Por qué**
- El guionista necesita ver el flujo completo.
- Pero la edición debe seguir siendo panel por panel y globo por globo.

> Nota: el Compositor no “genera” artísticamente la página con IA.
> Solo la arma como un editor: así se mantiene control y editabilidad.

---

## 6. Flujo general del sistema (paso a paso)

1) El usuario sube Docs, Layout, fichas e imágenes.
2) Ingesta clasifica y extrae contenido.
3) Canonical Builder construye/actualiza “la verdad oficial”.
4) Planner divide guión en páginas/paneles y crea un plan por panel.
5) Dialogue Structurer extrae diálogos y los deja listos para globos.
6) Por cada panel:
   - Reference Selector crea el paquete de referencias.
   - Prompt Builder arma el prompt por capas.
   - Image Generator crea la imagen del panel.
   - Continuity + Quality Gate validan.
   - Si hay fallos: se reintenta o se edita una zona.
7) Page Composer arma la vista orgánica por página.
8) El usuario revisa, edita prompts, mueve paneles y globos.
9) Export final.

---

## 7. Edición por panel (lo que el usuario puede hacer)

### 7.1. Editar un panel con su propio prompt
- Cambiar descripción del panel (“más dramático”, “más oscuro”, etc.)
- Cambiar estilo de ese panel sin romper el global (si se permite)
- Pedir variantes

### 7.2. Corregir una parte del panel (edición localizada)
- Seleccionar una zona (ej. la cara)
- Escribir un prompt específico para esa zona
- Mantener el resto intacto

### 7.3. Ampliar y recortar (sin perder calidad)
- Si el panel se redimensiona, se puede ampliar el fondo en lugar de estirar la imagen.

---

## 8. Reglas para evitar inconsistencias

- Lo que está en el Canonical Store se respeta siempre.
- Si el Vector Store trae algo que contradice el Canonical Store:
  - se marca como conflicto
  - se pide decisión o se aplica una regla predeterminada
- Continuity Supervisor mantiene estado entre paneles y páginas.
- Cada panel guarda su historial para volver atrás.

---

## 9. Qué significa “hecho” (criterio de éxito)

- Un personaje se ve reconocible y consistente a lo largo del cómic.
- El estilo se mantiene estable.
- El usuario puede ajustar panel por panel sin “romper todo”.
- Los globos se pueden editar como objetos (texto y posición).
- El guionista puede leer el cómic en páginas completas (vista orgánica).
- El sistema soporta iteración rápida: variantes y correcciones locales.

---

## 10. Notas de implementación (sin entrar demasiado en tecnología)

- El flujo se implementa como un conjunto de pasos coordinados (un “orquestador”).
- Cada paso guarda resultados intermedios para poder:
  - retomar si algo falla
  - reintentar sin repetir todo
  - mantener versiones por panel
- La generación de paneles puede ocurrir en paralelo para acelerar.

---

Fin del documento.
