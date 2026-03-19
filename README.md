# API de Encuestas Poblacionales — GEIH DANE 2024

API REST para recolección y validación de datos de encuestas demográficas en Colombia. Construida con **FastAPI** y **Pydantic v2**.

El sistema actúa como una **aduana transaccional**: cualquier dato inválido es rechazado antes de entrar al repositorio de análisis.

## Autores
- Cristian Vallejo
- Natalia González

USTA 2026
---

## Dataset

Microdatos reales de la **Gran Encuesta Integrada de Hogares (GEIH) — Diciembre 2024** del DANE.

- 61,246 registros procesados
- Variables: departamento, sexo, edad, estrato (1–6), área geográfica, nivel educativo, afiliación a salud

---

## Despliegue (Live Demo)
El proyecto se encuentra desplegado y funcional en: 
🚀 [https://encuesta-api-vhq1.onrender.com](https://encuesta-api-vhq1.onrender.com)


## Instalación
```bash
# 1. Clonar el repositorio
git clone https://github.com/CristianVallejo0104/Encuesta_API.git
cd Encuesta_API

# 2. Crear entorno virtual
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Ejecución
```bash
uvicorn main:app --reload
```

| URL | Descripción |
|-----|-------------|
| http://127.0.0.1:8000 | Interfaz web |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/redoc | Redoc |

---

## Endpoints

| Verbo | Ruta | Descripción | Status |
|-------|------|-------------|--------|
| POST | /encuestas/ | Registrar encuesta | 201 |
| GET | /encuestas/ | Listar todas | 200 |
| GET | /encuestas/estadisticas/ | Resumen estadístico demográfico | 200 |
| GET | /encuestas/estadisticas/respuestas/ | Estadísticas de respuestas | 200 |
| GET | /encuestas/exportar/json | Exportar encuestas en JSON | 200 |
| GET | /encuestas/exportar/pickle | Exportar encuestas en Pickle | 200 |
| GET | /encuestas/{id} | Obtener por ID | 200 / 404 |
| PUT | /encuestas/{id} | Actualizar | 200 / 404 |
| DELETE | /encuestas/{id} | Eliminar | 204 / 404 |
---

## Validaciones

| Campo | Regla |
|-------|-------|
| Edad | 0 – 120 años |
| Estrato | 1 – 6 (clasificación DANE) |
| Departamento | Lista oficial DIVIPOLA — 32 dptos. + Bogotá D.C. |
| Likert | 1 – 5 |
| Porcentaje | 0.0 – 100.0 |
| Binaria | si / no / 1 / 0 |

---

## Estructura
```
Encuesta_api/
├── main.py              # Punto de entrada — endpoints + decorador + manejador 422
├── models.py            # Modelos Pydantic — Encuestado, RespuestaEncuesta, EncuestaCompleta
├── validators.py        # Listas de referencia DANE
├── cliente_csv.py       # Script cliente — carga CSV y genera reporte con pandas
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

## Tests
```bash
pytest tests/ -v
```

38 tests — 21 unitarios (modelos) + 17 de integración (endpoints).

## Tecnologías

| Librería | Versión |
|----------|---------|
| FastAPI | 0.133.1 |
| Pydantic | 2.12.5 |
| Uvicorn | 0.41.0 |
| Pandas | 3.0.1 |
| pytest | 9.0.2 |
| Python | 3.13.12 |