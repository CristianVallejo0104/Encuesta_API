# API de Encuestas Poblacionales — GEIH DANE 2024

API REST construida con FastAPI que simula un sistema de recolección
y validación de datos demográficos basado en la Gran Encuesta Integrada
de Hogares (GEIH) Diciembre 2024 del DANE.

## Instalación
```bash
# 1. Clonar el repositorio
git clone https://github.com/CristianVallejo0104/Encuesta_API.git
cd Encuesta_API

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno virtual
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 4. Instalar dependencias
pip install -r requirements.txt
```

## Ejecución
```bash
uvicorn main:app --reload
```

Abrir en el navegador:
- **Swagger UI** → http://127.0.0.1:8000/docs
- **Redoc**       → http://127.0.0.1:8000/redoc
- **Interfaz**    → http://127.0.0.1:8000/

## Endpoints

| Verbo  | Ruta                     | Descripción                | Status  |
|--------|--------------------------|----------------------------|---------|
| POST   | /encuestas/              | Registrar encuesta         | 201     |
| GET    | /encuestas/              | Listar todas las encuestas | 200     |
| GET    | /encuestas/{id}          | Obtener encuesta por ID    | 200/404 |
| PUT    | /encuestas/{id}          | Actualizar encuesta        | 200/404 |
| DELETE | /encuestas/{id}          | Eliminar encuesta          | 204/404 |
| GET    | /encuestas/estadisticas/ | Resumen estadístico        | 200     |

## Dataset

Datos reales procesados de la GEIH Diciembre 2024 — DANE.
- 61,246 registros limpios
- Variables: departamento, sexo, edad, estrato (1-6), área, nivel educativo

Script de procesamiento: `scripts/preparardatos.py`

## Tests
```bash
pytest tests/ -v
```

38 tests — 21 unitarios (modelos) + 17 de integración (endpoints).

## Estructura
```
Encuesta_api/
├── main.py          # FastAPI + endpoints + decorador @log_request
├── models.py        # Modelos Pydantic (Encuestado, RespuestaEncuesta, EncuestaCompleta)
├── validators.py    # Validadores DANE (departamentos, estratos, niveles educativos)
├── requirements.txt
├── README.md
├── datos/
│   └── geih_diciembre_2024_limpio.csv
├── scripts/
│   └── preparardatos.py
└── tests/
    ├── test_models.py
    └── test_endpoints.py
```

## Tecnologías

- **FastAPI** 0.133.1
- **Pydantic** 2.12.5
- **Pandas** 3.0.1
- **pytest** 9.0.2
- **Python** 3.13.12