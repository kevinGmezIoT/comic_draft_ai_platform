# Guia de Desarrollo Local - Comic Draft AI

Para agilizar el desarrollo y evitar el uso constante de Docker durante las pruebas, seguiremos estos pasos para configurar el entorno local usando **`uv`** para Python y **`npm`** para el Frontend.

## 1. Instalación de `uv`
Como tienes Anaconda, puedes instalar `uv` fácilmente desde tu terminal principal:

```bash
pip install uv
```

---

## 2. Terminal 1: Backend (Django)

Navega a la carpeta `backend/`.

### Configuración inicial:
```bash
cd backend
# Instalar dependencias y crear entorno virtual automáticamente
uv sync
# Activar entorno (Windows)
.venv\Scripts\activate
```

### Ejecución:
Asegúrate de tener un archivo `.env` configurado. Si usas una base de datos local (PostgreSQL o SQLite), ajusta la `DATABASE_URL`.
```bash
python manage.py migrate
python manage.py runserver
```
El backend correrá en: `http://localhost:8000`

---

## 3. Terminal 2: Agent (Flask + Celery)

Navega a la carpeta `agent/`.

### Configuración inicial:
```bash
cd agent
# Instalar dependencias y crear entorno virtual automáticamente
uv sync
# Activar entorno (Windows)
.venv\Scripts\activate
```

### Ejecución:
El agente necesita interactuar con el backend y posiblemente con Redis para Celery.
```bash
# Para correr la API del agente (Flask)
python app.py

# (Opcional) Si necesitas correr el worker de Celery en otra terminal:
# celery -A worker.celery_app worker --loglevel=info
```
El agente correrá en: `http://localhost:8001` (o el puerto configurado en `app.py`).

---

## 4. Terminal 3: Frontend (Vite + React)

Navega a la carpeta `frontend/`.

### Configuración inicial:
```bash
cd frontend
npm install
```

### Ejecución:
Vite permite Hot Module Replacement (HMR), por lo que verás los cambios al instante.
```bash
npm run dev
```
El frontend correrá en: `http://localhost:5173` (o el puerto que indique Vite).

---

## Notas Importantes

1.  **Base de Datos y Redis**: Ahora que los puertos están expuestos en el `docker-compose.yml`, puedes usarlos desde fuera:
    ```bash
    docker compose up db redis -d
    ```
2.  **Variables de Entorno**: Actualiza tus archivos `.env` locales:
    - **Backend (`backend/.env`)**:
      ```env
      DATABASE_URL=postgres://user:pass@localhost:5432/comic_db
      REDIS_URL=redis://localhost:6379/0
      ```
    - **Agent (`agent/.env`)**:
      ```env
      REDIS_URL=redis://localhost:6379/0
      BACKEND_INTERNAL_URL=http://localhost:8000
      ```
    - **Frontend (`frontend/.env`)**:
      ```env
      VITE_API_URL=http://localhost:8000
      ```
3.  **Uso de uv**: `uv` es extremadamente rápido. Si quieres añadir una librería, usa `uv add <libreria>`. Esto actualizará automáticamente el `pyproject.toml`.
