"""
Punto de entrada de la API de Encuestas Poblacionales GEIH-DANE 2024.

Arrancar con: uvicorn main:app --reload
Swagger UI  : http://127.0.0.1:8000/docs
Redoc       : http://127.0.0.1:8000/redoc
"""

import time
import logging
import functools
from collections import Counter
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from models import EncuestaCompleta, EncuestaDB, EstadisticasResponse

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("encuesta_api")

# =============================================================================
# INSTANCIA FASTAPI
# =============================================================================
app = FastAPI(
    title="API de Encuestas Poblacionales — GEIH DANE 2024",
    description=(
        "Sistema de recolección y validación de datos de encuestas demográficas "
        "en Colombia. Basado en la estructura de variables de la Gran Encuesta "
        "Integrada de Hogares (GEIH) Diciembre 2024 del DANE.\n\n"
        "**Validaciones:** edad (0-120), estrato DANE (1-6), "
        "32 departamentos DIVIPOLA, escala Likert (1-5), porcentajes (0-100)."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "Encuestas", "description": "Operaciones CRUD sobre encuestas."},
        {"name": "Estadísticas", "description": "Resumen estadístico del repositorio."},
        {"name": "Sistema", "description": "Estado de la API."},
    ]
)

# =============================================================================
# BASE DE DATOS EN MEMORIA
# =============================================================================
db_encuestas: dict[str, EncuestaDB] = {}

# =============================================================================
# DECORADOR PERSONALIZADO: @log_request
# ─────────────────────────────────────────────────────────────────────────────
# Un decorador es una función que envuelve a otra función para añadirle
# comportamiento sin modificar su código original.
#
# Relación con FastAPI: @app.get(), @app.post() también son decoradores —
# registran la función como handler de una ruta HTTP.
# Nuestro @log_request se compone SOBRE los decoradores de ruta de FastAPI,
# añadiendo logging y métricas de tiempo a cada endpoint.
# =============================================================================
def log_request(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        inicio = time.perf_counter()
        logger.info(f"▶ Inicio: {func.__name__} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            resultado = await func(*args, **kwargs)
            ms = (time.perf_counter() - inicio) * 1000
            logger.info(f"✔ Fin: {func.__name__} | {ms:.2f} ms")
            return resultado
        except Exception as exc:
            logger.error(f"✖ Error en {func.__name__}: {exc}")
            raise
    return wrapper

# =============================================================================
# RF4: MANEJADOR PERSONALIZADO DE ERRORES HTTP 422
# =============================================================================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Intercepta errores de validación Pydantic antes del 422 genérico.
    Retorna JSON estructurado con detalle de cada campo inválido
    y registra el intento fallido en el log.
    """
    errores = [
        {
            "campo": " → ".join(str(loc) for loc in err["loc"]),
            "mensaje": err["msg"],
            "tipo_error": err["type"],
            "valor_recibido": err.get("input", "N/A"),
        }
        for err in exc.errors()
    ]

    logger.warning(
        f"⚠ Ingesta rechazada | Ruta: {request.url.path} | "
        f"Errores: {len(errores)}"
    )

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "codigo_http": 422,
            "mensaje": "Los datos contienen errores de validación estadística.",
            "ruta": str(request.url.path),
            "total_errores": len(errores),
            "errores": errores,
            "ayuda": "Consulte /docs para ver los formatos válidos.",
        },
    )

# =============================================================================
# RF3: ENDPOINTS CRUD
# =============================================================================

# ── POST /encuestas/ ─────────────────────────────────────────────────────────
@app.post(
    "/encuestas/",
    response_model=EncuestaDB,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nueva encuesta",
    description=(
        "Valida y registra una encuesta completa.\n\n"
        "**`async def` vs `def` en FastAPI:**\n"
        "- `def`: FastAPI delega a un thread pool para no bloquear el event loop.\n"
        "- `async def`: corre directamente en el event loop. "
        "Indispensable cuando se hacen awaits a I/O no bloqueante "
        "(bases de datos async, HTTP externo).\n\n"
        "**ASGI:** FastAPI corre sobre ASGI (Asynchronous Server Gateway Interface), "
        "que permite miles de conexiones concurrentes en un solo proceso, "
        "a diferencia de WSGI que bloquea un thread por request."
    ),
    tags=["Encuestas"]
)
@log_request
async def crear_encuesta(encuesta: EncuestaCompleta) -> EncuestaDB:
    nueva = EncuestaDB(**encuesta.model_dump())
    db_encuestas[nueva.id] = nueva
    logger.info(f"✔ Encuesta registrada | ID: {nueva.id} | Encuestado: {nueva.encuestado.nombre}")
    return nueva


# ── GET /encuestas/ ──────────────────────────────────────────────────────────
@app.get(
    "/encuestas/",
    response_model=List[EncuestaDB],
    summary="Listar todas las encuestas",
    description="Retorna todas las encuestas registradas en memoria.",
    tags=["Encuestas"]
)
@log_request
async def listar_encuestas() -> List[EncuestaDB]:
    return list(db_encuestas.values())


# ── GET /encuestas/estadisticas/ ─────────────────────────────────────────────
@app.get(
    "/encuestas/estadisticas/",
    response_model=EstadisticasResponse,
    summary="Resumen estadístico",
    description="Calcula estadísticas descriptivas de todas las encuestas registradas.",
    tags=["Estadísticas"]
)
@log_request
async def obtener_estadisticas() -> EstadisticasResponse:
    encuestas = list(db_encuestas.values())

    if not encuestas:
        return EstadisticasResponse(
            total_encuestas=0,
            promedio_edad=0.0,
            mediana_edad=0.0,
            distribucion_estrato={},
            distribucion_departamento={},
            distribucion_sexo={},
            distribucion_nivel_educativo={},
            promedio_respuestas_por_encuesta=0.0,
        )

    edades = sorted(e.encuestado.edad for e in encuestas)
    n = len(edades)
    mediana = (
        edades[n // 2] if n % 2 != 0
        else (edades[n // 2 - 1] + edades[n // 2]) / 2
    )

    return EstadisticasResponse(
        total_encuestas=n,
        promedio_edad=round(sum(edades) / n, 2),
        mediana_edad=round(mediana, 2),
        distribucion_estrato=dict(Counter(str(e.encuestado.estrato) for e in encuestas)),
        distribucion_departamento=dict(Counter(e.encuestado.departamento for e in encuestas)),
        distribucion_sexo=dict(Counter(e.encuestado.sexo for e in encuestas)),
        distribucion_nivel_educativo=dict(Counter(e.encuestado.nivel_educativo or "no_especificado" for e in encuestas)),
        promedio_respuestas_por_encuesta=round(sum(len(e.respuestas) for e in encuestas) / n, 2),
    )


# ── GET /encuestas/{id} ──────────────────────────────────────────────────────
@app.get(
    "/encuestas/{encuesta_id}",
    response_model=EncuestaDB,
    summary="Obtener encuesta por ID",
    description="Retorna una encuesta por su UUID. HTTP 404 si no existe.",
    tags=["Encuestas"]
)
@log_request
async def obtener_encuesta(encuesta_id: str) -> EncuestaDB:
    if encuesta_id not in db_encuestas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe encuesta con ID '{encuesta_id}'."
        )
    return db_encuestas[encuesta_id]


# ── PUT /encuestas/{id} ──────────────────────────────────────────────────────
@app.put(
    "/encuestas/{encuesta_id}",
    response_model=EncuestaDB,
    summary="Actualizar encuesta",
    description="Reemplaza los datos de una encuesta existente.",
    tags=["Encuestas"]
)
@log_request
async def actualizar_encuesta(encuesta_id: str, datos: EncuestaCompleta) -> EncuestaDB:
    if encuesta_id not in db_encuestas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe encuesta con ID '{encuesta_id}'."
        )
    original = db_encuestas[encuesta_id]
    actualizada = EncuestaDB(
        **datos.model_dump(),
        id=original.id,
        registrado_en=original.registrado_en,
    )
    db_encuestas[encuesta_id] = actualizada
    logger.info(f"✏ Encuesta actualizada | ID: {encuesta_id}")
    return actualizada


# ── DELETE /encuestas/{id} ───────────────────────────────────────────────────
@app.delete(
    "/encuestas/{encuesta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar encuesta",
    description="Elimina una encuesta permanentemente.",
    tags=["Encuestas"]
)
@log_request
async def eliminar_encuesta(encuesta_id: str) -> None:
    if encuesta_id not in db_encuestas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe encuesta con ID '{encuesta_id}'."
        )
    del db_encuestas[encuesta_id]
    logger.info(f"🗑 Encuesta eliminada | ID: {encuesta_id}")


# ── GET / ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Sistema"], summary="Estado de la API")
async def raiz():
    return {
        "api": "API de Encuestas Poblacionales — GEIH DANE 2024",
        "version": "1.0.0",
        "estado": "operativa",
        "encuestas_en_memoria": len(db_encuestas),
        "documentacion": {"swagger": "/docs", "redoc": "/redoc"},
    }