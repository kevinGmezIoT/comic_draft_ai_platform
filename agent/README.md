# ComicDraft AI - Orchestration Agent 🤖🎨

Este módulo es el "cerebro" de la plataforma, encargado de transformar guiones y documentos heterogéneos en un borrador de cómic estructurado y visualmente coherente. La orquestación se basa en un grafo de estados utilizando **LangGraph**.

## 🧠 Proceso de Orquestación Multi-Agente

La orquestación no es un simple pipeline lineal, sino un flujo de trabajo de "agentes especializados" que comparten un estado común (`AgentState`). A continuación se detalla el ciclo de vida de una generación:

### 1. RAG & Ingestion (El Documentalista)
*   **Función**: Digiere archivos PDF, DOCX o TXT.
*   **Proceso**: Utiliza LangChain para cargar y fragmentar los datos. Los fragmentos se almacenan en una base de datos vectorial (**ChromaDB**).
*   **Resultado**: Extrae dos piezas clave: un resumen general del estilo/mundo y el guion narrativo completo.

### 2. World Model Building (El Arquitecto de Consistencia)
*   **Función**: Establece las bases visuales antes de que se dibuje un solo panel.
*   **Proceso**: Un LLM analiza el resumen del mundo para identificar personajes principales y escenarios recurrentes.
*   **Consistencia**: Registra a cada personaje en el `CharacterManager`. Si el guion dice que el héroe tiene un brazo robótico, este rasgo se fija aquí para que todos los paneles posteriores lo hereden.

### 3. Strategic Planning (El Director de Arte)
*   **Función**: Descompone la narrativa en una estructura visual.
*   **Proceso**: Utiliza **GPT-4o** para razonar sobre el ritmo (pacing) de la historia. Decide cuántas páginas tendrá el cómic y qué sucede en cada panel.
*   **Salida**: Genera una lista de `PanelSpecs` con:
    *   Descripción de la escena.
    *   Personajes presentes.
    *   Composición del plano (close-up, wide-shot, etc.).
    *   **Visual Prompt**: Un prompt enriquecido diseñado específicamente para modelos de imagen (DALL-E 3 / Titan).

### 4. Consistent Image Generation (El Artista Visual)
*   **Función**: Ejecuta la producción de las imágenes.
*   **Proceso**: Itera sobre la lista de paneles generada por el Director de Arte. Para cada panel:
    1.  Consulta la "Biblia de Personajes" para obtener sus rasgos visuales fijados.
    2.  Combina el prompt de escena con los rasgos de los personajes y el estilo global.
    3.  Llama al adaptador correspondiente (OpenAI o AWS Bedrock).
*   **Dependencia de Paneles**: La duración de esta fase es directamente proporcional a la cantidad de paneles. Si el guion requiere 20 paneles, el agente realizará 20 llamadas secuenciales (o en batches) a los modelos de imagen.

---

## 📊 Escalabilidad y Dependencias

### Relación con la cantidad de paneles
La complejidad del proceso crece linealmente con el número de paneles decididos por el **Narrative Planner**. 
*   **Paneles < 10**: Procesamiento rápido, ideal para prototipado.
*   **Paneles > 30**: El sistema utiliza **Celery** y **Redis** para manejar la generación en segundo plano sin bloquear la API. El usuario recibe actualizaciones en tiempo real a medida que cada imagen se completa.

### Especialización de Sub-Agentes (Nodos)

| Agente | Herramienta Clave | Responsabilidad |
| :--- | :--- | :--- |
| **Documentalista** | LangChain / Chroma | Memoria a largo plazo y contexto. |
| **Arquitecto** | GPT-4o / CharacterManager | Consistencia visual del personaje. |
| **Director de Arte** | GPT-4o (Vision logic) | Layout, encuadre y prompts técnicos. |
| **Artista** | DALL-E 3 / Titan G1 | Renderizado final de la imagen. |

## 🛠️ Detalles Técnicos
El estado del proyecto se mantiene durante toda la ejecución en el objeto `AgentState`, lo que permite que, si un paso falla (por ejemplo, un error de red en el panel 5), el proceso pueda reintentarse o informar exactamente en qué fase se detuvo la orquestación.
