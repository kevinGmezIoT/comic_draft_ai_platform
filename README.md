# Comic Draft AI Platform - Prototipo

Este repositorio contiene la estructura base para una plataforma de generación y edición de cómics asistida por IA.

## Estrategia de Arquitectura Avanzada

El sistema ahora soporta flujos asíncronos y robustez para producción:

1.  **Ingesta RAG (Retrieval-Augmented Generation)**: El agente usa `ChromaDB` para indexar documentos (PDF/Docx) y extraer reglas del mundo y rasgos de personajes, garantizando que los páneles generados respeten el material fuente.
2.  **Consistencia de Personajes**: Implementamos un `CharacterManager` que utiliza descripciones y referencias visuales para inyectar contexto específico en cada prompt de panel.
3.  **Procesamiento Asíncrono (Worker Strategy)**:
    *   El **Backend** guarda los assets en S3 y encola una tarea.
    *   El **Agent Worker (Celery)** recupera los archivos, corre el grafo de LangGraph y genera imágenes en segundo plano.
    *   Al terminar, el worker notifica al Backend mediante un **Webhook**, el cual organiza los páneles por página y orden correcto para el renderizado.
4.  **Orquestación de Imágenes**: El agente asegura el orden jerárquico (`Página > Panel`) permitiendo que la UI renderice el cómic exactamente como fue planeado por el motor de IA.

## Requisitos Previos
- Docker & Docker Compose
- API Keys (OpenAI, AWS Bedrock)

## Ejecución con Docker (Recomendado)
```bash
docker-compose up --build
```

## Ejecución Manual (Local)

### 1. Redis (Requerido para la cola)
```bash
# Tener redis corriendo en localhost:6379
```

### 2. Agent Service & Worker (Flask + Celery)
```bash
cd agent
# Terminal 1: API
python app.py
# Terminal 2: Worker
celery -A worker.celery_app worker --pool=solo --loglevel=info
```

### 2. Backend (Django)
Gestión de datos y proyectos.
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # Configura DB y Agent URL
python manage.py migrate
python manage.py runserver
```

### 3. Frontend (React)
Interfaz intuitiva.
```bash
cd frontend
npm install
cp .env.example .env      # Configura el URL del Backend
npm run dev
```

## Organización del Código

- **Flexibilidad de Modelos**: En `agent/core/adapters/`, se implementa el patrón *Adapter* para abstraer la generación de imágenes, permitiendo rotar entre proveedores sin cambiar el flujo de LangGraph.
- **Estado Persistente**: El `backend` guarda todo el historial de prompts y versiones de cada panel, permitiendo regenerar o editar partes específicas.
- **Detección de Fuentes**: El agente procesa documentos (PDF/DOCX) para extraer "Biblias de Personaje" y guiones, transformándolos en un estado estructurado.
