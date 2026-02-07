1. **Normalización semántica de fuentes heterogéneas**

   * El guión profesional (con convenciones de panel, página, SFX, captions, beats), fichas de personaje, notas sueltas y reseñas rara vez están en un formato uniforme.
   * Problema: convertir todo a un **schema canónico** (“story world model”) sin perder intención (tono, ritmo, subtexto, restricciones) ni mezclar versiones contradictorias.

2. **Desambiguación y resolución de referencias**

   * En guiones reales hay pronombres, apodos, “ELLA”, “EL TIPO”, referencias cruzadas (“como en la pág. 3”), y cambios de vestuario implícitos.
   * Problema: resolver **coreference** y **entity linking** para mapear cada línea/acción a personajes/props/locaciones correctas.

3. **Segmentación correcta en páginas/paneles (comic grammar)**

   * El guión puede describir: composición, tamaño de panel, transición (cut, match, smash), ritmo, silencios.
   * Problema: el “panelizer” debe preservar **pacing** y **continuidad visual**; si parte mal, todo lo demás colapsa.

4. **Generación de “panel specs” con suficiente control**

   * Un panel spec útil debe incluir: encuadre, lente (equivalente), ángulo, blocking, expresión, iluminación, fondo, props, estilo, DOF, acción, énfasis.
   * Problema: si el spec es pobre o inconsistente, el motor de imagen tenderá a alucinar o simplificar.

5. **Consistencia de personajes (la piedra angular)**

   * Mantener rasgos invariantes (rostro, complexión, cabello, accesorios, paleta) a través de decenas de paneles, con poses y expresiones distintas.
   * Problema: los modelos generalistas derivan (“identity drift”). Sin estrategia (refs, embeddings, LoRA, inpainting iterativo) la coherencia cae.

6. **Consistencia de estilo artístico**

   * El estilo debe ser estable (línea, sombreado, textura, paleta, grano, tipo de acabado) aunque cambie la escena.
   * Problema: los modelos pueden fluctuar entre estilos “cercanos”; además el mismo prompt no siempre produce el mismo look.

7. **Continuidad de vestuario, props y estado**

   * El guión asume estado persistente: heridas, suciedad, objetos en mano, clima, hora del día, roturas.
   * Problema: necesitas un **state tracker** por escena/personaje para que el prompt/edición lleve “memoria” de continuidad.

8. **Coherencia espacial y geográfica (blocking + layout)**

   * En secuencias de acción: “180-degree rule”, direcciones de mirada, posiciones relativas.
   * Problema: sin un modelo espacial, los paneles contradicen izquierda/derecha, distancias, entradas/salidas.

9. **Control de composición y legibilidad (pensado para globos)**

   * Los paneles deben dejar “aire” para diálogos y captions, sin tapar rostros o acciones clave.
   * Problema: la generación tiende a llenar el encuadre; luego los globos tapan contenido o quedan ilegibles.

10. **Calidad de texto en imagen (SFX, letreros, onomatopeyas)**

* La mayoría de modelos aún fallan en tipografía precisa dentro de la imagen.
* Problema: conviene **separar lettering** como capa vectorial/HTML/canvas; pero entonces debes integrar SFX y señales diegéticas coherentes con la escena.

11. **Edición localizada por prompt (inpainting/outpainting) robusta**

* Tu requisito de “editar cada imagen con su prompt” exige máscaras, selección de regiones, y coherencia con el resto del panel.
* Problema: inpainting puede introducir artefactos, cambiar identidad o iluminación; outpainting puede romper perspectiva.

12. **Gestión de prompts por capas y conflictos**

* Prompts de personaje, fondo, estilo, restricciones y negativos pueden pelear entre sí.
* Problema: necesitas un **prompt compiler** (prioridades, “atoms”, validación) para no degradar la salida por concatenación naïve.

13. **Dependencia del proveedor/modelo y variabilidad**

* Diferentes motores (OpenAI/Bedrock/Stability) tienen distintas capacidades (negatives, seeds, controlnets, masks).
* Problema: abstraer sin perder features; y manejar drift cuando el proveedor actualiza modelos.

14. **Versionado y trazabilidad de assets (panel-level)**

* Para ser “altamente personalizable”, el usuario iterará mucho: variantes, rollback, branching.
* Problema: diseñar un sistema de versiones eficiente (metadatos + diffs + assets en S3) y reproducible.

15. **Costo y latencia a escala (cómic completo)**

* Un cómic puede tener 60–150 paneles; cada panel puede requerir 3–10 iteraciones.
* Problema: costos explosivos + colas largas. Necesitas estrategias: preview low-res, caching, batch, prioridades, cuotas.

16. **Detección de inconsistencias internas en el input**

* Fichas y notas pueden contradecirse (edad, color de ojos, timeline).
* Problema: reconciliación automática vs. pedir intervención; necesitas “conflict resolver” con UI para decisiones.

17. **RAG multimodal “de verdad” (no sólo texto)**

* Referencias visuales (bocetos) deben influir en generación.
* Problema: embeddings de imagen + recuperación relevante + selección de “mejores refs” por panel, evitando meter ruido.

18. **Evaluación automática de coherencia (quality gates)**

* ¿Cómo detectas que “Ana” cambió de cara o que el estilo derivó?
* Problema: métricas no triviales: face similarity, CLIP similarity, hashing perceptual, heurísticas de paleta; más evaluación con LLM (con riesgo de subjetividad).

19. **Moderación/safety sin romper flujos creativos**

* Los guiones pueden incluir violencia, temas sensibles, etc., y los modelos tienen políticas variables.
* Problema: filtros demasiado estrictos bloquean; demasiado laxos generan riesgo. Necesitas clasificación contextual y modos de “safe rephrase”.

20. **UX técnica del editor (canvas) con datos pesados**

* Manejar páginas grandes, múltiples capas, zoom, selección, snapping, reflow de texto, thumbnails.
* Problema: rendimiento (memoria/CPU), serialización del documento, y sincronización colaborativa si se agrega multi-user.

21. **Export profesional (PDF/print)**

* CMYK vs RGB, sangrado, resolución, fuentes embebidas, antialiasing, kerning.
* Problema: lo generado suele estar en RGB; hay que asegurar que el export sea consistente y no degrade.

22. **Internacionalización y convenciones de lectura**

* Izq→der vs der→izq (manga), tipografías, reglas de globos y onomatopeyas.
* Problema: layout y composición cambian; el “planner” debe soportar estas variantes.

23. **Derechos de entrenamiento/uso de referencias (PI)**

* Usuarios pueden subir material protegido o pedir estilos de artistas vivos.
* Problema: cumplimiento y policy: prevención, logging, y herramientas de “style distancing”.

24. **Reproducibilidad (o falta de ella)**

* Aun con seed, algunos proveedores no garantizan determinismo completo; cambios de modelo rompen la reproducción.
* Problema: si el usuario quiere “regenerar igual pero con X”, necesitas almacenar todo el contexto y aceptar que no siempre es idéntico.

Si te sirve, puedo convertir esta lista en un **backlog técnico** con épicas/historias, criterios de aceptación y una priorización tipo MVP vs V1 (con los “must-have” para lograr coherencia y personalización desde el día 1).
