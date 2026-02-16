# Comic Draft AI Platform - Enterprise Grade 🤖🎨

![Logo](https://img.shields.io/badge/Status-Production--Ready-green)
![Tech](https://img.shields.io/badge/Stack-Django%20%7C%20React%20%7C%20LangGraph-blue)

**Comic Draft AI** es una plataforma integral abierta de orquestación para la generación de cómics asistida por Inteligencia Artificial. No es solo un generador de imágenes; es un motor de narrativa visual que garantiza coherencia, persistencia y control creativo total.

Está orientado a guionistas y personas que tengan una historia en mente y desean verla en un cómic. La generación tendrá mejores resultados mientras más contexto se le brinde como: guión en formato pdf especificando páginas y viñetas, imágenes de referencia de personajes y escenarios, layouts de las páginas y estilos.

**Se debe usar como una herramienta de apoyo para la creación de cómics y NO como un generador final de cómics.**

---

## 🧠 Arquitectura del Sistema

El proyecto se divide en tres pilares fundamentales que trabajan en armonía:

### 1. El Agente ("El Cerebro")
Ubicado en `/agent`, utiliza **LangGraph** para ejecutar un flujo de trabajo cíclico (DAG) que simula el proceso de creación de un Cómic en borrados:
- **Ingesta RAG**: Indexa documentos en `ChromaDB` para asegurar que la historia sea fiel al material original.
- **Entendimiento de Historia**: Extrae propósitos narrativos y resúmenes por página.
- **World Model Builder**: Construye el **Canon** del proyecto (Personajes y Escenarios) para mantener la identidad visual.
- **Planner & Layout**: Actúa como Director de Arte, definiendo la composición técnica de cada panel.
- **Generación Multimodal**: Produce imágenes enriquecidas con contexto inyectado dinámicamente.

### 2. El Backend ("El Coordinador")
Desarrollado en **Django**, actúa como el centro de persistencia y gestión:
- **Gestión de Proyectos**: Almacena "Biblias del Mundo", guías de estilo y notas globales.
- **Persistencia de Datos**: La BD (PostgreSQL) guarda cada versión de panel, prompts generados, relaciones entre personajes y referencias visuales.
- **Cola de Tareas**: Gestiona la comunicación asíncrona mediante **Amazon SQS** para procesar la generación de imágenes sin bloquear la UI.
- **Assets**: Organiza y sirve archivos desde **AWS S3**.

### 3. El Frontend ("La Interfaz")
Una aplicación **React** moderna diseñada para la eficiencia:
- **Dashboard de Proyectos**: Visualiza el progreso y gestiona el mundo del cómic.
- **Editor Canvas**: Permite editar globos de texto, reubicar paneles y previsualizar la página final.
- **Wizard de Creación**: Guía al usuario desde el guion hasta el canon visual.

---

## 🚀 Despliegue Local (Docker)

La forma más rápida de levantar la plataforma completa (excepto el agente que requiere claves externas) es desde la **raíz del proyecto**:

### 1. Configuración de Entorno
Asegúrate de tener los archivos `.env` en sus respectivas carpetas:
- [backend/.env](file:///backend/.env)
- [frontend/.env](file:///frontend/.env)

### 2. Lanzamiento
```bash
docker-compose up --build
```
Esto levantará:
- **Nginx**: Proxy inverso en puerto `80`.
- **Frontend**: Build de producción optimizado.
- **Backend API**: Servido por Gunicorn.
- **Worker/Consumer**: Procesador de cola SQS.
- **Database**: PostgreSQL.

Accede a la plataforma en: `http://localhost`.

---

## ☁️ Despliegue en AWS

### 1. El Agente (Agent Core)
El agente está diseñado para ejecutarse sobre **Amazon Bedrock Agent Core**.
1. Instala `agentcore` en la carpeta `agent/`.
2. Configura tu `.bedrock_agentcore.yaml`.
3. Despliega usando:
   ```bash
   cd agent
   agentcore launch --env ...
   ```
*Consulta el [README detallado del agente](file:///agent/README.md) para más detalles.*

### 2. El Main Stack (Backend + Frontend)
Sigue esta estrategia:
- **Base de Datos**: Usa **Amazon RDS (PostgreSQL)**.
- **Almacenamiento**: Configura un bucket **S3** para `MEDIA_URL`.
- **Computación**: Despliega el `docker-compose.yml` en **Amazon ECS (Fargate)** o sube las imágenes a **ECR**.
- **CDN**: Sirve los estáticos del frontend desde **S3 + CloudFront** para máxima velocidad.

---

## 📂 Organización de Archivos

- `/agent`: Lógica de IA, LangGraph, RAG y Adaptadores de imagen.
- `/backend`: API REST, Modelos de datos, Gestión de colas.
- `/frontend`: Código fuente de React, Componentes y Canvas.
- `/nginx`: Configuración del proxy para producción.
- `docker-compose.yml`: Orquestación raíz.

---

*Desarrollado para el futuro de la narrativa visual.*
