"""
Punto de entrada de la API de Encuestas Poblacionales GEIH-DANE 2024.

Arrancar con: uvicorn main:app --reload
Swagger UI  : http://127.0.0.1:8000/docs
Redoc       : http://127.0.0.1:8000/redoc
"""

import time
import logging
import functools
import pickle
import json
import base64
from collections import Counter
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, HTMLResponse
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
    version="1.2.0",
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

# ── GET /encuestas/estadisticas/ ──────────────────────────────────────────────────────────
@app.get("/encuestas/estadisticas/", response_model=EstadisticasResponse, tags=["Estadísticas"],
         summary="Resumen estadístico demográfico",
         description="Calcula conteo, promedio y mediana de edad, y distribuciones por estrato, departamento, sexo, nivel educativo y afiliación a salud.")
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
            nivel_educativo={},
            afiliacion_salud={"si": 0, "no": 0},
            promedio_respuestas_por_encuesta=0.0,
        )

    # 1. Cálculos de edad
    edades = sorted(e.encuestado.edad for e in encuestas)
    n = len(edades)
    mediana = (edades[n // 2] if n % 2 != 0 else (edades[n // 2 - 1] + edades[n // 2]) / 2)

    # 2. Conteo de Salud (¡Súper importante!)
    salud_counts = {"si": 0, "no": 0}
    for e in encuestas:
        if e.encuestado.afiliado_salud:
            salud_counts["si"] += 1
        else:
            salud_counts["no"] += 1

    # 3. Respuesta final (Nombres exactos de tu clase)
    return EstadisticasResponse(
        total_encuestas=n,
        promedio_edad=round(sum(edades) / n, 2),
        mediana_edad=round(mediana, 2),
        distribucion_estrato=dict(sorted(Counter(str(e.encuestado.estrato) for e in encuestas).items())),
        distribucion_departamento=dict(Counter(e.encuestado.departamento for e in encuestas).most_common()),
        distribucion_sexo=dict(Counter(e.encuestado.sexo for e in encuestas)),
        nivel_educativo=dict(Counter(e.encuestado.nivel_educativo or "no_especificado" for e in encuestas)),
        afiliacion_salud=salud_counts,
        promedio_respuestas_por_encuesta=round(sum(len(e.respuestas) for e in encuestas) / n, 2),
    )

# ── GET /encuestas/estadisticas/respuestas/ ──────────────────────────────
@app.get(
    "/encuestas/estadisticas/respuestas/",
    summary="Estadísticas de respuestas",
    description="Calcula estadísticas descriptivas de las respuestas de la encuesta.",
    tags=["Estadísticas"]
)
@log_request
async def estadisticas_respuestas():
    encuestas = list(db_encuestas.values())

    if not encuestas:
        return {
            "p01_promedio_satisfaccion": 0,
            "p02_promedio_calidad_vida": 0,
            "p03_promedio_gasto_alimentacion": 0,
            "p04_acceso_internet": {"si": 0, "no": 0},
            "p05_preocupaciones": {}
        }

    p01_vals, p02_vals, p03_vals, p04_vals, p05_vals = [], [], [], [], []

    for enc in encuestas:
        for resp in enc.respuestas:
            if resp.pregunta_id == "P01":
                p01_vals.append(float(resp.valor))
            elif resp.pregunta_id == "P02":
                p02_vals.append(float(resp.valor))
            elif resp.pregunta_id == "P03":
                p03_vals.append(float(resp.valor))
            elif resp.pregunta_id == "P04":
                p04_vals.append(str(resp.valor).lower())
            elif resp.pregunta_id == "P05":
                p05_vals.append(str(resp.valor))

    # Contar P04
    p04_si = p04_vals.count("si") + p04_vals.count("sí")
    p04_no = p04_vals.count("no")

    # Contar P05 top 5
    p05_top = dict(Counter(p05_vals).most_common(5))

    return {
        "p01_promedio_satisfaccion": round(sum(p01_vals)/len(p01_vals), 2) if p01_vals else 0,
        "p02_promedio_calidad_vida": round(sum(p02_vals)/len(p02_vals), 2) if p02_vals else 0,
        "p03_promedio_gasto_alimentacion": round(sum(p03_vals)/len(p03_vals), 2) if p03_vals else 0,
        "p04_acceso_internet": {"si": p04_si, "no": p04_no},
        "p05_preocupaciones": p05_top
    }

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


# ── GET /encuestas/exportar/json ─────────────────────────────────────────────
@app.get(
    "/encuestas/exportar/json",
    summary="Exportar encuestas en formato JSON",
    description="""
    Exporta todas las encuestas almacenadas en formato JSON.
    JSON es legible, portable y estándar universal para APIs REST.
    """,
    tags=["Estadísticas"]
)
@log_request
async def exportar_json():
    encuestas = [e.model_dump() for e in db_encuestas.values()]
    serializado = json.dumps(
        encuestas,
        ensure_ascii=False,
        indent=2,
        default=str
    )
    return {
        "formato": "JSON",
        "total_registros": len(encuestas),
        "tamanio_bytes": len(serializado.encode("utf-8")),
        "legible_humanos": True,
        "interoperable": True,
        "datos": encuestas,
        "nota": "JSON es el estándar para APIs REST. Legible, portable y seguro."
    }


# ── GET /encuestas/exportar/pickle ───────────────────────────────────────────
@app.get(
    "/encuestas/exportar/pickle",
    summary="Exportar encuestas en formato Pickle",
    description="""
    Exporta todas las encuestas en formato Pickle (binario Python).
    Los datos se retornan codificados en Base64 para viajar en JSON.
    Advertencia: nunca deserialices Pickle de fuentes no confiables.
    """,
    tags=["Estadísticas"]
)
@log_request
async def exportar_pickle():
    encuestas = list(db_encuestas.values())
    datos_pickle = pickle.dumps(encuestas)
    datos_base64 = base64.b64encode(datos_pickle).decode("utf-8")
    datos_json = json.dumps([e.model_dump() for e in encuestas], default=str)
    tamanio_json = len(datos_json.encode("utf-8"))
    tamanio_pickle = len(datos_pickle)
    return {
        "formato": "Pickle",
        "total_registros": len(encuestas),
        "tamanio_pickle_bytes": tamanio_pickle,
        "tamanio_json_bytes": tamanio_json,
        "ahorro_bytes": tamanio_json - tamanio_pickle,
        "legible_humanos": False,
        "interoperable": False,
        "solo_python": True,
        "datos_base64": datos_base64,
        "advertencia": "Nunca deserialices Pickle de fuentes no confiables.",
        "como_deserializar": "import pickle, base64; datos = pickle.loads(base64.b64decode(datos_base64))",
        "nota": "Pickle es útil para caché interno, nunca para APIs públicas."
    }


# ── GET / — Interfaz web ─────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, tags=["Sistema"], summary="Interfaz web")
async def raiz():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Encuestas GEIH — DANE 2024</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --primario: #1a56db;
    --primario-oscuro: #1341b0;
    --fondo: #f8fafc;
    --blanco: #ffffff;
    --gris-100: #f1f5f9;
    --gris-200: #e2e8f0;
    --gris-400: #94a3b8;
    --gris-700: #334155;
    --gris-900: #0f172a;
    --verde: #16a34a;
    --rojo: #dc2626;
    --amarillo: #d97706;
    --borde: #e2e8f0;
    --sombra: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    --sombra-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.05);
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Inter',sans-serif; background:var(--fondo); color:var(--gris-900); min-height:100vh; }

  /* HEADER */
  header {
    background:var(--blanco);
    border-bottom:1px solid var(--borde);
    padding:0 32px;
    display:flex; align-items:center; justify-content:space-between;
    height:64px; position:sticky; top:0; z-index:100;
    box-shadow:var(--sombra);
  }
  .header-left { display:flex; align-items:center; gap:12px; }
  .logo {
    width:36px; height:36px; background:var(--primario);
    border-radius:8px; display:flex; align-items:center;
    justify-content:center; font-size:18px;
  }
  .header-title { font-size:16px; font-weight:700; color:var(--gris-900); }
  .header-sub { font-size:12px; color:var(--gris-400); margin-top:1px; }
  .badge-api {
    background:#eff6ff; color:var(--primario);
    border:1px solid #bfdbfe; border-radius:20px;
    padding:3px 10px; font-size:11px; font-weight:600;
  }

  /* LAYOUT */
  .container { max-width:1200px; margin:0 auto; padding:32px 24px; }

  /* STATS TOP */
  .stats-row { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:28px; }
  .stat-card {
    background:var(--blanco); border:1px solid var(--borde);
    border-radius:12px; padding:20px 24px;
    box-shadow:var(--sombra);
  }
  .stat-card .label { font-size:12px; color:var(--gris-400); text-transform:uppercase; letter-spacing:0.5px; font-weight:500; }
  .stat-card .valor { font-size:28px; font-weight:700; color:var(--gris-900); margin-top:4px; }
  .stat-card .sub { font-size:12px; color:var(--gris-400); margin-top:2px; }

  /* GRID PRINCIPAL */
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  .full { grid-column:1/-1; }

  /* CARDS */
  .card {
    background:var(--blanco); border:1px solid var(--borde);
    border-radius:12px; box-shadow:var(--sombra);
    overflow:hidden;
  }
  .card-header {
    padding:16px 24px; border-bottom:1px solid var(--borde);
    display:flex; align-items:center; gap:10px;
  }
  .card-header h2 { font-size:15px; font-weight:600; color:var(--gris-900); }
  .card-body { padding:24px; }

  /* FORMULARIO */
  .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .form-group { display:flex; flex-direction:column; gap:5px; }
  .form-group.full { grid-column:1/-1; }
  label { font-size:12px; font-weight:500; color:var(--gris-700); }
  input, select, textarea {
    border:1px solid var(--borde); border-radius:8px;
    padding:9px 12px; font-family:'Inter',sans-serif;
    font-size:14px; color:var(--gris-900); background:var(--blanco);
    outline:none; transition:border 0.15s;
  }
  input:focus, select:focus, textarea:focus { border-color:var(--primario); box-shadow:0 0 0 3px rgba(26,86,219,0.1); }
  textarea { resize:vertical; min-height:80px; }

  /* BOTONES */
  .btn {
    display:inline-flex; align-items:center; justify-content:center;
    gap:6px; padding:9px 20px; border-radius:8px; border:none;
    font-family:'Inter',sans-serif; font-size:14px; font-weight:500;
    cursor:pointer; transition:all 0.15s;
  }
  .btn-primary { background:var(--primario); color:#fff; }
  .btn-primary:hover { background:var(--primario-oscuro); }
  .btn-outline {
    background:transparent; color:var(--gris-700);
    border:1px solid var(--borde);
  }
  .btn-outline:hover { background:var(--gris-100); }
  .btn-danger { background:#fef2f2; color:var(--rojo); border:1px solid #fecaca; }
  .btn-danger:hover { background:#fee2e2; }
  .btn-sm { padding:5px 12px; font-size:12px; }

  /* RESPUESTAS */
  .respuestas-container { display:flex; flex-direction:column; gap:10px; margin-bottom:14px; }
  .respuesta-item {
    background:var(--gris-100); border:1px solid var(--borde);
    border-radius:8px; padding:12px 14px;
    display:grid; grid-template-columns:80px 100px 1fr auto; gap:10px; align-items:center;
  }

  /* TABLA */
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead tr { background:var(--gris-100); }
  th { padding:10px 14px; text-align:left; font-size:11px; font-weight:600; color:var(--gris-400); text-transform:uppercase; letter-spacing:0.5px; }
  td { padding:12px 14px; border-bottom:1px solid var(--borde); color:var(--gris-700); }
  tr:last-child td { border-bottom:none; }
  tr:hover td { background:var(--gris-100); }

  /* BADGES */
  .badge { display:inline-block; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:600; }
  .badge-verde { background:#dcfce7; color:#15803d; }
  .badge-azul { background:#dbeafe; color:#1d4ed8; }
  .badge-gris { background:var(--gris-100); color:var(--gris-400); }

  /* ALERTAS */
  .alert { border-radius:8px; padding:12px 16px; font-size:13px; margin-top:14px; display:none; }
  .alert.visible { display:block; }
  .alert-success { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
  .alert-error { background:#fef2f2; border:1px solid #fecaca; color:#b91c1c; }
  .alert-info { background:#eff6ff; border:1px solid #bfdbfe; color:#1e40af; }

  /* GRÁFICAS */
  .chart-container { display:flex; flex-direction:column; gap:8px; }
  .chart-bar-row { display:flex; align-items:center; gap:10px; font-size:13px; }
  .chart-bar-label { width:120px; color:var(--gris-700); font-size:12px; text-align:right; flex-shrink:0; }
  .chart-bar-track { flex:1; background:var(--gris-100); border-radius:4px; height:22px; overflow:hidden; }
  .chart-bar-fill { height:100%; background:var(--primario); border-radius:4px; display:flex; align-items:center; padding-left:8px; color:#fff; font-size:11px; font-weight:600; transition:width 0.5s ease; min-width:30px; }
  .chart-bar-val { width:40px; color:var(--gris-400); font-size:12px; }

  /* SEARCH */
  .search-box { display:flex; gap:10px; margin-bottom:16px; }
  .search-box input { flex:1; }

  /* EMPTY */
  .empty { text-align:center; padding:40px; color:var(--gris-400); }
  .empty-icon { font-size:36px; margin-bottom:8px; }

  /* TABS */
  .tabs { display:flex; gap:4px; border-bottom:1px solid var(--borde); margin-bottom:20px; }
  .tab {
    padding:10px 16px; font-size:13px; font-weight:500;
    color:var(--gris-400); cursor:pointer; border-bottom:2px solid transparent;
    margin-bottom:-1px; transition:all 0.15s;
  }
  .tab.active { color:var(--primario); border-bottom-color:var(--primario); }

  .spinner { display:inline-block; width:14px; height:14px; border:2px solid #fff; border-top-color:transparent; border-radius:50%; animation:spin 0.6s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style>
</head>
<body>

<header>
  <div class="header-left">
    <div class="logo">📊</div>
    <div>
      <div class="header-title">Encuestas Poblacionales</div>
      <div class="header-sub">GEIH — DANE Diciembre 2024</div>
    </div>
  </div>
  <span class="badge-api">API v1.1.6</span>
</header>

<div class="container">

  <div class="stats-row" id="stats-top">
    <div class="stat-card">
      <div class="label">Encuestas registradas</div>
      <div class="valor" id="st-total">—</div>
      <div class="sub">en memoria</div>
    </div>
    <div class="stat-card">
      <div class="label">Promedio de edad</div>
      <div class="valor" id="st-edad">—</div>
      <div class="sub">años</div>
    </div>
    <div class="stat-card">
      <div class="label">Mediana de edad</div>
      <div class="valor" id="st-mediana">—</div>
      <div class="sub">años</div>
    </div>
    <div class="stat-card">
      <div class="label">Resp. por encuesta</div>
      <div class="valor" id="st-resp">—</div>
      <div class="sub">promedio</div>
    </div>
  </div>

  <div class="grid">

   <div class="card">
      <div class="card-header">
        <span>📝</span>
        <h2>Registrar encuesta</h2>
      </div>
      <div class="card-body">
        <div class="form-grid">
          <div class="form-group full">
            <label>Nombre completo</label>
            <input type="text" id="f-nombre" placeholder="Ej: María García">
          </div>
          <div class="form-group">
            <label>Edad</label>
            <input type="number" id="f-edad" placeholder="0 – 120" min="0" max="120">
          </div>
          <div class="form-group">
            <label>Sexo</label>
            <input list="lista-sexo" id="f-sexo" placeholder="Ej: F o M">
            <datalist id="lista-sexo">
              <option value="F">F — Femenino</option>
              <option value="M">M — Masculino</option>
            </datalist>
          </div>
          <div class="form-group">
            <label>Estrato DANE (1–6)</label>
            <input type="number" list="lista-estrato" id="f-estrato" placeholder="Ej: 3">
            <datalist id="lista-estrato">
              <option value="1"></option><option value="2"></option><option value="3"></option>
              <option value="4"></option><option value="5"></option><option value="6"></option>
            </datalist>
          </div>
          <div class="form-group">
            <label>Departamento</label>
            <input list="lista-departamento" id="f-departamento" placeholder="Escribe o selecciona...">
            <datalist id="lista-departamento">
              <option value="Amazonas"></option><option value="Antioquia"></option><option value="Arauca"></option>
              <option value="Atlántico"></option><option value="Bogotá D.C."></option><option value="Bolívar"></option>
              <option value="Boyacá"></option><option value="Caldas"></option><option value="Caquetá"></option>
              <option value="Casanare"></option><option value="Cauca"></option><option value="Cesar"></option>
              <option value="Chocó"></option><option value="Córdoba"></option><option value="Cundinamarca"></option>
              <option value="Guainía"></option><option value="Guaviare"></option><option value="Huila"></option>
              <option value="La Guajira"></option><option value="Magdalena"></option><option value="Meta"></option>
              <option value="Nariño"></option><option value="Norte de Santander"></option><option value="Putumayo"></option>
              <option value="Quindío"></option><option value="Risaralda"></option>
              <option value="San Andrés y Providencia"></option><option value="Santander"></option>
              <option value="Sucre"></option><option value="Tolima"></option><option value="Valle del Cauca"></option>
              <option value="Vaupés"></option><option value="Vichada"></option>
            </datalist>
          </div>
          <div class="form-group">
            <label>Área geográfica</label>
            <input list="lista-area" id="f-area" placeholder="Ej: cabecera">
            <datalist id="lista-area">
              <option value="cabecera">Cabecera municipal</option>
              <option value="rural_disperso">Rural disperso</option>
            </datalist>
          </div>
          <div class="form-group">
            <label>Nivel educativo</label>
            <input list="lista-nivel" id="f-nivel" placeholder="Ej: secundario">
            <datalist id="lista-nivel">
              <option value="ninguno"></option><option value="primaria"></option><option value="secundaria"></option>
              <option value="tecnico"></option><option value="tecnologico"></option><option value="universitario"></option><option value="posgrado"></option>
            </datalist>
          </div>
          <div class="form-group">
            <label>Afiliado a salud</label>
            <select id="f-salud">
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          </div>
        </div>

        <div style="margin:16px 0 8px">
          <label style="font-size:13px;font-weight:600;color:var(--gris-900)">
            Respuestas de la encuesta — GEIH 2024
          </label>
          <p style="font-size:11px;color:var(--gris-400);margin-top:3px">
            Preguntas basadas en variables reales de la Gran Encuesta Integrada de Hogares — DANE
          </p>
        </div>

        <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px">
          <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:8px;padding:12px 14px">
            <span style="font-size:11px;font-weight:600;color:var(--primario);background:#eff6ff;padding:2px 8px;border-radius:4px">P01 — Likert (1 a 5)</span>
            <label style="font-size:12px;color:var(--gris-700);margin:8px 0 6px;display:block">¿Qué tan satisfecho está con los servicios públicos de su municipio?</label>
            <select id="p01-valor" style="width:100%;font-size:13px">
              <option value="">— Seleccione —</option>
              <option value="1">1 — Muy insatisfecho</option>
              <option value="2">2 — Insatisfecho</option>
              <option value="3">3 — Neutral</option>
              <option value="4">4 — Satisfecho</option>
              <option value="5">5 — Muy satisfecho</option>
            </select>
          </div>
          <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:8px;padding:12px 14px">
            <span style="font-size:11px;font-weight:600;color:var(--primario);background:#eff6ff;padding:2px 8px;border-radius:4px">P02 — Likert (1 a 5)</span>
            <label style="font-size:12px;color:var(--gris-700);margin:8px 0 6px;display:block">¿Cómo califica su calidad de vida en el último año?</label>
            <select id="p02-valor" style="width:100%;font-size:13px">
              <option value="">— Seleccione —</option>
              <option value="1">1 — Muy mala</option>
              <option value="2">2 — Mala</option>
              <option value="3">3 — Regular</option>
              <option value="4">4 — Buena</option>
              <option value="5">5 — Muy buena</option>
            </select>
          </div>
          <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:8px;padding:12px 14px">
            <span style="font-size:11px;font-weight:600;color:#15803d;background:#dcfce7;padding:2px 8px;border-radius:4px">P03 — Porcentaje (0 a 100)</span>
            <label style="font-size:12px;color:var(--gris-700);margin:8px 0 6px;display:block">¿Qué porcentaje de sus ingresos destina a alimentación?</label>
            <input type="number" id="p03-valor" placeholder="Ej: 45.5" min="0" max="100" step="0.1" style="width:100%;font-size:13px">
          </div>
          <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:8px;padding:12px 14px">
            <span style="font-size:11px;font-weight:600;color:#d97706;background:#fef3c7;padding:2px 8px;border-radius:4px">P04 — Binaria (si / no)</span>
            <label style="font-size:12px;color:var(--gris-700);margin:8px 0 6px;display:block">¿Su hogar tiene acceso a internet?</label>
            <select id="p04-valor" style="width:100%;font-size:13px">
              <option value="">— Seleccione —</option>
              <option value="si">Sí</option>
              <option value="no">No</option>
            </select>
          </div>
          <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:8px;padding:12px 14px">
            <span style="font-size:11px;font-weight:600;color:#7c3aed;background:#ede9fe;padding:2px 8px;border-radius:4px">P05 — Texto libre</span>
            <label style="font-size:12px;color:var(--gris-700);margin:8px 0 6px;display:block">¿Cuál es su principal preocupación en su municipio?</label>
            <input type="text" id="p05-valor" placeholder="Ej: Falta de empleo, inseguridad..." style="width:100%;font-size:13px">
          </div>
        </div>

        <div class="alert" id="alert-registro"></div>
        <button id="btn-registrar" class="btn btn-primary" style="width:100%" onclick="registrarEncuesta()">
          Registrar encuesta
        </button>
      </div>
    </div>

    <div style="display:flex;flex-direction:column;gap:20px">

      <div class="card">
        <div class="card-header">
          <span>🔍</span>
          <h2>Buscar encuesta por ID</h2>
        </div>
        <div class="card-body">
          <div class="search-box">
            <input type="text" id="buscar-id" placeholder="UUID de la encuesta...">
            <button class="btn btn-primary" onclick="buscarPorId()">Buscar</button>
          </div>
          <div id="resultado-busqueda"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>👥</span>
          <h2>Demografía y Salud</h2>
        </div>
        <div class="card-body">
          <div style="margin-bottom:15px">
            <label style="font-size:11px; color:var(--gris-400); text-transform:uppercase; font-weight:600;">Distribución por Sexo</label>
            <div id="chart-sexo" class="chart-container" style="margin-top:8px"></div>
          </div>
          <hr style="border:0; border-top:1px solid var(--borde); margin:15px 0">
          <div>
            <label style="font-size:11px; color:var(--gris-400); text-transform:uppercase; font-weight:600;">Afiliación a Salud</label>
            <div id="stat-salud" style="display:flex; gap:10px; margin-top:8px"></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>🎓</span>
          <h2>Nivel Educativo</h2>
        </div>
        <div class="card-body">
          <div id="chart-educacion" class="chart-container"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>📈</span>
          <h2>Distribución por estrato</h2>
        </div>
        <div class="card-body">
          <div class="chart-container" id="chart-estrato">
            <div class="empty"><div class="empty-icon">📊</div><div>Sin datos aún</div></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>🗺️</span>
          <h2>Top departamentos</h2>
        </div>
        <div class="card-body">
          <div class="chart-container" id="chart-depto">
            <div class="empty"><div class="empty-icon">📊</div><div>Sin datos aún</div></div>
          </div>
        </div>
      </div>

    </div>

    <div class="card full">
      <div class="card-header">
        <span>📊</span>
        <h2>Estadísticas de respuestas — GEIH 2024</h2>
      </div>
      <div class="card-body">
        <p style="font-size:11px;color:var(--gris-400);margin-bottom:16px">
          Basado en preguntas reales de la Gran Encuesta Integrada de Hogares — DANE
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">

          <div>
            <div style="margin-bottom:14px">
              <div style="font-size:12px;font-weight:600;color:var(--gris-700);margin-bottom:4px">P01 — Satisfacción con servicios públicos</div>
              <div style="display:flex;align-items:center;gap:10px">
                <div style="flex:1;background:var(--gris-100);border-radius:4px;height:22px;overflow:hidden">
                  <div id="bar-p01" style="height:100%;background:var(--primario);border-radius:4px;display:flex;align-items:center;padding-left:8px;color:#fff;font-size:11px;font-weight:600;transition:width 0.5s;width:0%">0</div>
                </div>
                <span id="val-p01" style="font-size:12px;color:var(--gris-400);width:60px">— / 5</span>
              </div>
            </div>
            <div style="margin-bottom:14px">
              <div style="font-size:12px;font-weight:600;color:var(--gris-700);margin-bottom:4px">P02 — Calidad de vida</div>
              <div style="display:flex;align-items:center;gap:10px">
                <div style="flex:1;background:var(--gris-100);border-radius:4px;height:22px;overflow:hidden">
                  <div id="bar-p02" style="height:100%;background:#7c3aed;border-radius:4px;display:flex;align-items:center;padding-left:8px;color:#fff;font-size:11px;font-weight:600;transition:width 0.5s;width:0%">0</div>
                </div>
                <span id="val-p02" style="font-size:12px;color:var(--gris-400);width:60px">— / 5</span>
              </div>
            </div>
            <div>
              <div style="font-size:12px;font-weight:600;color:var(--gris-700);margin-bottom:4px">P03 — Gasto en alimentación (% promedio)</div>
              <div style="display:flex;align-items:center;gap:10px">
                <div style="flex:1;background:var(--gris-100);border-radius:4px;height:22px;overflow:hidden">
                  <div id="bar-p03" style="height:100%;background:#16a34a;border-radius:4px;display:flex;align-items:center;padding-left:8px;color:#fff;font-size:11px;font-weight:600;transition:width 0.5s;width:0%">0%</div>
                </div>
                <span id="val-p03" style="font-size:12px;color:var(--gris-400);width:60px">—%</span>
              </div>
            </div>
          </div>

          <div>
            <div style="margin-bottom:14px">
              <div style="font-size:12px;font-weight:600;color:var(--gris-700);margin-bottom:6px">P04 — Acceso a internet</div>
              <div style="display:flex;gap:10px">
                <div style="flex:1;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px;text-align:center">
                  <div id="val-p04-si" style="font-size:20px;font-weight:700;color:#15803d">—</div>
                  <div style="font-size:11px;color:#15803d">Sí tienen</div>
                </div>
                <div style="flex:1;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px;text-align:center">
                  <div id="val-p04-no" style="font-size:20px;font-weight:700;color:#dc2626">—</div>
                  <div style="font-size:11px;color:#dc2626">No tienen</div>
                </div>
              </div>
            </div>
            <div>
              <div style="font-size:12px;font-weight:600;color:var(--gris-700);margin-bottom:6px">P05 — Principales preocupaciones</div>
              <div id="chart-p05" style="display:flex;flex-direction:column;gap:4px">
                <div style="text-align:center;color:var(--gris-400);font-size:12px">Sin datos aún</div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>

    <div class="card full">
      <div class="card-header">
        <span>📋</span>
        <h2>Encuestas registradas</h2>
        <button class="btn btn-outline btn-sm" style="margin-left:auto" onclick="cargarEncuestas()">↻ Actualizar</button>
      </div>
      <div class="card-body" style="padding:0">
        <div id="tabla-encuestas">
          <div class="empty"><div class="empty-icon">📋</div><div>No hay encuestas registradas aún</div></div>
        </div>
      </div>

  </div>
</div>

<script>
const API = window.location.origin;

// ── Agregar/quitar respuestas ─────────────────────────────────────────────
function agregarRespuesta() {
  const cont = document.getElementById("respuestas-lista");
  const n = cont.children.length + 1;
  const id = String(n).padStart(2,"0");
  const div = document.createElement("div");
  div.className = "respuesta-item";
  div.innerHTML = `
    <input placeholder="P${id}" value="P${id}" style="font-size:13px">
    <select style="font-size:13px">
      <option value="likert">Likert</option>
      <option value="porcentaje">Porcentaje</option>
      <option value="binaria">Binaria</option>
      <option value="texto">Texto</option>
    </select>
    <input placeholder="Valor" style="font-size:13px">
    <button class="btn btn-danger btn-sm" onclick="eliminarRespuesta(this)">✕</button>
  `;
  cont.appendChild(div);
}

function eliminarRespuesta(btn) {
  const cont = document.getElementById("respuestas-lista");
  if (cont.children.length > 1) btn.closest(".respuesta-item").remove();
}

// ── Registrar encuesta ────────────────────────────────────────────────────
async function registrarEncuesta() {
    const alertDiv = document.getElementById("alert-registro");
    alertDiv.className = "alert";
    const nombre = document.getElementById("f-nombre").value.trim();
    const edad = document.getElementById("f-edad").value;
    const p01 = document.getElementById("p01-valor").value;
    const p02 = document.getElementById("p02-valor").value;
    const p03 = document.getElementById("p03-valor").value;
    const p04 = document.getElementById("p04-valor").value;
    const p05 = document.getElementById("p05-valor").value.trim();

    if (nombre.length < 2) {
      alertDiv.className = "alert alert-error visible";
      alertDiv.innerHTML = "❌ El nombre debe tener al menos 2 caracteres.";
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (!edad || parseInt(edad) < 0 || parseInt(edad) > 120) {
      alertDiv.className = "alert alert-error visible";
      alertDiv.innerHTML = "❌ La edad debe estar entre 0 y 120 años.";
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (!p01 || !p02 || !p03 || !p04 || !p05) {
    alertDiv.className = "alert alert-error visible";
    alertDiv.innerHTML = "❌ Por favor completa todas las preguntas de la encuesta.";
    alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });;
    return;
    }

    const respuestas = [
    {
        pregunta_id: "P01",
        enunciado: "¿Qué tan satisfecho está con los servicios públicos de su municipio?",
        tipo_pregunta: "likert",
        valor: parseInt(p01)
    },
    {
        pregunta_id: "P02",
        enunciado: "¿Cómo califica su calidad de vida en el último año?",
        tipo_pregunta: "likert",
        valor: parseInt(p02)
    },
    {
        pregunta_id: "P03",
        enunciado: "¿Qué porcentaje de sus ingresos destina a alimentación?",
        tipo_pregunta: "porcentaje",
        valor: parseFloat(p03)
    },
    {
        pregunta_id: "P04",
        enunciado: "¿Su hogar tiene acceso a internet?",
        tipo_pregunta: "binaria",
        valor: p04
    },
    {
        pregunta_id: "P05",
        enunciado: "¿Cuál es su principal preocupación en su municipio?",
        tipo_pregunta: "texto",
        valor: p05
    }
    ];

  const payload = {
    encuestado: {
      nombre: nombre,
      edad: parseInt(edad),
      sexo: document.getElementById("f-sexo").value,
      estrato: parseInt(document.getElementById("f-estrato").value),
      departamento: document.getElementById("f-departamento").value,
      area: document.getElementById("f-area").value,
      nivel_educativo: document.getElementById("f-nivel").value,
      afiliado_salud: document.getElementById("f-salud").value === "true"
    },
    respuestas,
    fuente: "Interfaz-Web"
  };

  try {
    const r = await fetch(`${API}/encuestas/`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (r.status === 201) {
      alertDiv.className = "alert alert-success visible";
      alertDiv.innerHTML = `✅ Encuesta registrada correctamente. ID: <code style="font-size:11px">${data.id}</code>`;
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
      // Limpiar formulario
      document.getElementById("f-nombre").value = "";
      document.getElementById("f-edad").value = "";
      document.getElementById("p01-valor").value = "";
      document.getElementById("p02-valor").value = "";
      document.getElementById("p03-valor").value = "";
      document.getElementById("p04-valor").value = "";
      document.getElementById("p05-valor").value = "";
      cargarEstadisticas();
      cargarEncuestas();
      cargarEstadisticasRespuestas();
    } else {
      const errores = data.errores?.map(e => `<li><b>${e.campo}</b>: ${e.mensaje}</li>`).join("") || "";
      alertDiv.className = "alert alert-error visible";
      alertDiv.innerHTML = `❌ Error de validación:<ul style="margin-top:6px;padding-left:16px">${errores}</ul>`;
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } catch(e) {
    alertDiv.className = "alert alert-error visible";
    alertDiv.innerHTML = "❌ No se pudo conectar con la API.";
    alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

// ── Buscar por ID ─────────────────────────────────────────────────────────
async function buscarPorId() {
  const id = document.getElementById("buscar-id").value.trim();
  const div = document.getElementById("resultado-busqueda");
  if (!id) return;
  try {
    const r = await fetch(`${API}/encuestas/${id}`);
    if (r.status === 404) {
      div.innerHTML = `<div class="alert alert-error visible">❌ No se encontró ninguna encuesta con ese ID.</div>`;
      return;
    }
    const d = await r.json();
    div.innerHTML = `
      <div style="background:var(--gris-100);border:1px solid var(--borde);border-radius:10px;padding:16px;font-size:13px">
        <div style="font-weight:600;font-size:15px;margin-bottom:10px">${d.encuestado.nombre}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;color:var(--gris-700)">
          <div>📍 <b>Departamento:</b> ${d.encuestado.departamento}</div>
          <div>🎂 <b>Edad:</b> ${d.encuestado.edad} años</div>
          <div>⚡ <b>Estrato:</b> ${d.encuestado.estrato}</div>
          <div>🎓 <b>Nivel:</b> ${d.encuestado.nivel_educativo}</div>
          <div>👤 <b>Sexo:</b> ${d.encuestado.sexo === 'M' ? 'Masculino' : 'Femenino'}</div>
          <div>🏥 <b>Salud:</b> ${d.encuestado.afiliado_salud ? "Afiliado" : "No afiliado"}</div>
          <div>🏘 <b>Área:</b> ${d.encuestado.area === 'cabecera' ? 'Cabecera municipal' : 'Rural disperso'}</div>
          <div>📦 <b>Fuente:</b> ${d.fuente || '—'}</div>
        </div>
        <div style="margin-top:10px;color:var(--gris-400);font-size:11px">
          ID: ${d.id} · Registrado: ${new Date(d.registrado_en).toLocaleString("es-CO")}
        </div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="btn btn-danger btn-sm" onclick="eliminarEncuesta('${d.id}')">🗑 Eliminar</button>
          <button class="btn btn-outline btn-sm" onclick="cargarParaEditar('${d.id}')">✏ Editar</button>
        </div>
      </div>`;
  } catch(e) {
    div.innerHTML = `<div class="alert alert-error visible">❌ Error conectando con la API.</div>`;
  }
}

// ── Eliminar encuesta ─────────────────────────────────────────────────────
async function eliminarEncuesta(id) {
  if (!confirm("¿Seguro que deseas eliminar esta encuesta?")) return;
  const r = await fetch(`${API}/encuestas/${id}`, {method:"DELETE"});
  if (r.status === 204) {
    document.getElementById("resultado-busqueda").innerHTML =
      `<div class="alert alert-info visible">🗑 Encuesta eliminada correctamente.</div>`;
    cargarEstadisticas();
    cargarEncuestas();
    cargarEstadisticasRespuestas();
  } else {
    document.getElementById("resultado-busqueda").innerHTML =
      `<div class="alert alert-error visible">❌ No se pudo eliminar la encuesta.</div>`;
  }
}
async function cargarParaEditar(id) {
  try {
    const r = await fetch(`${API}/encuestas/${id}`);
    const d = await r.json();

    // Rellenar formulario con datos existentes
    document.getElementById("f-nombre").value = d.encuestado.nombre;
    document.getElementById("f-edad").value = d.encuestado.edad;
    document.getElementById("f-sexo").value = d.encuestado.sexo;
    document.getElementById("f-estrato").value = d.encuestado.estrato;
    document.getElementById("f-departamento").value = d.encuestado.departamento;
    document.getElementById("f-area").value = d.encuestado.area;
    document.getElementById("f-nivel").value = d.encuestado.nivel_educativo;
    document.getElementById("f-salud").value = d.encuestado.afiliado_salud ? "true" : "false";

    // Rellenar respuestas si existen
    const resp = d.respuestas;
    resp.forEach(r => {
      const el = document.getElementById(`p0${r.pregunta_id.slice(-1)}-valor`);
      if (el) el.value = r.valor;
    });

    // Cambiar botón a modo edición
    const btn = document.getElementById("btn-registrar");
    btn.textContent = "✏ Actualizar encuesta";
    btn.onclick = () => actualizarEncuesta(id);

    // Añadir botón cancelar si no existe
    if (!document.getElementById("btn-cancelar-edicion")) {
      const cancelBtn = document.createElement("button");
      cancelBtn.id = "btn-cancelar-edicion";
      cancelBtn.className = "btn btn-outline";
      cancelBtn.style.width = "100%";
      cancelBtn.style.marginTop = "8px";
      cancelBtn.textContent = "✕ Cancelar edición";
      cancelBtn.onclick = cancelarEdicion;
      btn.parentNode.insertBefore(cancelBtn, btn.nextSibling);
    }

    // Scroll al formulario
    document.querySelector(".card").scrollIntoView({ behavior: "smooth" });

    document.getElementById("resultado-busqueda").innerHTML =
      `<div class="alert alert-info visible">✏ Editando encuesta. Modifica los datos y da clic en "Actualizar encuesta".</div>`;

  } catch(e) {
    console.error(e);
  }
}

async function actualizarEncuesta(id) {
  const alertDiv = document.getElementById("alert-registro");
  alertDiv.className = "alert";

  const p01 = document.getElementById("p01-valor").value;
  const p02 = document.getElementById("p02-valor").value;
  const p03 = document.getElementById("p03-valor").value;
  const p04 = document.getElementById("p04-valor").value;
  const p05 = document.getElementById("p05-valor").value;

  const payload = {
    encuestado: {
      nombre: document.getElementById("f-nombre").value,
      edad: parseInt(document.getElementById("f-edad").value),
      sexo: document.getElementById("f-sexo").value,
      estrato: parseInt(document.getElementById("f-estrato").value),
      departamento: document.getElementById("f-departamento").value,
      area: document.getElementById("f-area").value,
      nivel_educativo: document.getElementById("f-nivel").value,
      afiliado_salud: document.getElementById("f-salud").value === "true"
    },
    respuestas: [
      { pregunta_id: "P01", enunciado: "¿Qué tan satisfecho está con los servicios públicos?", tipo_pregunta: "likert", valor: parseInt(p01) },
      { pregunta_id: "P02", enunciado: "¿Cómo califica su calidad de vida?", tipo_pregunta: "likert", valor: parseInt(p02) },
      { pregunta_id: "P03", enunciado: "¿Qué porcentaje destina a alimentación?", tipo_pregunta: "porcentaje", valor: parseFloat(p03) },
      { pregunta_id: "P04", enunciado: "¿Acceso a internet?", tipo_pregunta: "binaria", valor: p04 },
      { pregunta_id: "P05", enunciado: "¿Principal preocupación?", tipo_pregunta: "texto", valor: p05 }
    ],
    fuente: "Interfaz-Web"
  };

  try {
    const r = await fetch(`${API}/encuestas/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await r.json();

    if (r.status === 200) {
      alertDiv.className = "alert alert-success visible";
      alertDiv.innerHTML = `✅ Encuesta actualizada correctamente.`;
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });

      // Restaurar botón a modo registro
      const btn = document.getElementById("btn-registrar");
      btn.textContent = "Registrar encuesta";
      btn.onclick = registrarEncuesta;
      const cancelBtn = document.getElementById("btn-cancelar-edicion");
      if (cancelBtn) cancelBtn.remove();

      cargarEstadisticas();
      cargarEncuestas();
      cargarEstadisticasRespuestas();
    } else {
      const errores = data.errores?.map(e => `<li><b>${e.campo}</b>: ${e.mensaje}</li>`).join("") || "";
      alertDiv.className = "alert alert-error visible";
      alertDiv.innerHTML = `❌ Error:<ul style="margin-top:6px;padding-left:16px">${errores}</ul>`;
      alertDiv.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } catch(e) {
    alertDiv.className = "alert alert-error visible";
    alertDiv.innerHTML = "❌ No se pudo conectar con la API.";
  }
}
async function cargarEstadisticasRespuestas() {
  try {
    const r = await fetch(`${API}/encuestas/estadisticas/respuestas/`);
    const d = await r.json();

    // P01
    const p01 = d.p01_promedio_satisfaccion;
    document.getElementById("bar-p01").style.width = `${(p01/5)*100}%`;
    document.getElementById("bar-p01").textContent = p01;
    document.getElementById("val-p01").textContent = `${p01} / 5`;

    // P02
    const p02 = d.p02_promedio_calidad_vida;
    document.getElementById("bar-p02").style.width = `${(p02/5)*100}%`;
    document.getElementById("bar-p02").textContent = p02;
    document.getElementById("val-p02").textContent = `${p02} / 5`;

    // P03
    const p03 = d.p03_promedio_gasto_alimentacion;
    document.getElementById("bar-p03").style.width = `${p03}%`;
    document.getElementById("bar-p03").textContent = `${p03}%`;
    document.getElementById("val-p03").textContent = `${p03}%`;

    // P04
    document.getElementById("val-p04-si").textContent = d.p04_acceso_internet.si;
    document.getElementById("val-p04-no").textContent = d.p04_acceso_internet.no;

    // P05
    const p05div = document.getElementById("chart-p05");
    const p05data = d.p05_preocupaciones;
    if (Object.keys(p05data).length === 0) {
      p05div.innerHTML = `<div style="text-align:center;color:var(--gris-400);font-size:12px">Sin datos aún</div>`;
    } else {
      const max = Math.max(...Object.values(p05data));
      p05div.innerHTML = Object.entries(p05data).map(([k,v]) => `
        <div style="display:flex;align-items:center;gap:8px;font-size:12px">
          <div style="width:100px;color:var(--gris-700);text-overflow:ellipsis;overflow:hidden;white-space:nowrap">${k}</div>
          <div style="flex:1;background:var(--gris-100);border-radius:4px;height:18px;overflow:hidden">
            <div style="height:100%;background:#d97706;border-radius:4px;width:${(v/max)*100}%"></div>
          </div>
          <div style="width:20px;color:var(--gris-400)">${v}</div>
        </div>`).join("");
    }
  } catch(e) {}
}



function cancelarEdicion() {
  const btn = document.getElementById("btn-registrar");
  btn.textContent = "Registrar encuesta";
  btn.onclick = registrarEncuesta;
  const cancelBtn = document.getElementById("btn-cancelar-edicion");
  if (cancelBtn) cancelBtn.remove();
  document.getElementById("resultado-busqueda").innerHTML = "";
}

// ── Cargar estadísticas ───────────────────────────────────────────────────
async function cargarEstadisticas() {
  try {
    const r = await fetch(`${API}/encuestas/estadisticas/`);
    const d = await r.json();

    document.getElementById("st-total").textContent = d.total_encuestas;
    document.getElementById("st-edad").textContent = d.promedio_edad || "—";
    document.getElementById("st-mediana").textContent = d.mediana_edad || "—";
    document.getElementById("st-resp").textContent = d.promedio_respuestas_por_encuesta || "—";

    // Gráfica sexo (NUEVO)
    const sexDiv = document.getElementById("chart-sexo");
    const sexData = d.distribucion_sexo;
    if (Object.keys(sexData).length === 0) {
      sexDiv.innerHTML = `<div style="text-align:center;color:var(--gris-400);font-size:12px">Sin datos</div>`;
    } else {
      sexDiv.innerHTML = Object.entries(sexData).map(([k,v]) => `
        <div class="chart-bar-row">
          <div class="chart-bar-label">${k == 'M' ? 'Hombre' : 'Mujer'}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="background:#3b82f6; width:${(v/d.total_encuestas)*100}%">${v}</div>
          </div>
        </div>`).join("");
    }

    // Afiliación Salud (NUEVO)
    const saludDiv = document.getElementById("stat-salud");
    const s = d.afiliacion_salud;
    saludDiv.innerHTML = `
        <div style="flex:1; background:#f0fdf4; padding:10px; border-radius:8px; text-align:center; border:1px solid #bbf7d0">
            <div style="color:#15803d; font-weight:700; font-size:18px">${s.si}</div><div style="font-size:10px; color:#15803d">Asegurados</div>
        </div>
        <div style="flex:1; background:#fef2f2; padding:10px; border-radius:8px; text-align:center; border:1px solid #fecaca">
            <div style="color:#dc2626; font-weight:700; font-size:18px">${s.no}</div><div style="font-size:10px; color:#dc2626">No Asegurados</div>
        </div>`;

    // Educación (NUEVO)
    const eduDiv = document.getElementById("chart-educacion");
    const eduData = d.nivel_educativo;
    if (Object.keys(eduData).length === 0) {
      eduDiv.innerHTML = `<div style="text-align:center;color:var(--gris-400);font-size:12px">Sin datos</div>`;
    } else {
      eduDiv.innerHTML = Object.entries(eduData).map(([k,v]) => `
        <div class="chart-bar-row">
          <div class="chart-bar-label" style="width:90px">${k}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="background:#64748b; width:${(v/d.total_encuestas)*100}%">${v}</div>
          </div>
        </div>`).join("");
    }

    // Gráfica estrato
    const estDiv = document.getElementById("chart-estrato");
    const estData = d.distribucion_estrato;
    const maxEst = Math.max(...Object.values(estData), 1);
    if (Object.keys(estData).length === 0) {
      estDiv.innerHTML = `<div class="empty"><div class="empty-icon">📊</div><div>Sin datos aún</div></div>`;
    } else {
      estDiv.innerHTML = Object.entries(estData).sort((a,b)=>a[0]-b[0]).map(([k,v]) => `
        <div class="chart-bar-row">
          <div class="chart-bar-label">Estrato ${k}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="width:${Math.max(v/maxEst*100,5)}%">${v}</div>
          </div>
          <div class="chart-bar-val">${v}</div>
        </div>`).join("");
    }

    // Gráfica departamento (top 5)
    const depDiv = document.getElementById("chart-depto");
    const depData = d.distribucion_departamento;
    const maxDep = Math.max(...Object.values(depData), 1);
    if (Object.keys(depData).length === 0) {
      depDiv.innerHTML = `<div class="empty"><div class="empty-icon">📊</div><div>Sin datos aún</div></div>`;
    } else {
      const top5 = Object.entries(depData).sort((a,b)=>b[1]-a[1]).slice(0,5);
      depDiv.innerHTML = top5.map(([k,v]) => `
        <div class="chart-bar-row">
          <div class="chart-bar-label">${k}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="width:${Math.max(v/maxDep*100,5)}%">${v}</div>
          </div>
          <div class="chart-bar-val">${v}</div>
        </div>`).join("");
    }
  } catch(e) {}
}

// ── Cargar tabla encuestas ────────────────────────────────────────────────
async function cargarEncuestas() {
  const div = document.getElementById("tabla-encuestas");
  try {
    const r = await fetch(`${API}/encuestas/`);
    const data = await r.json();
    if (data.length === 0) {
      div.innerHTML = `<div class="empty"><div class="empty-icon">📋</div><div>No hay encuestas registradas aún</div></div>`;
      return;
    }
    div.innerHTML = `
        <table>
            <thead>
            <tr>
                <th>Nombre</th><th>Depto.</th><th>Edad</th>
                <th>Estrato</th><th>Nivel educativo</th><th>Fuente</th>
                <th>ID</th><th>Acción</th>
            </tr>
            </thead>
            <tbody>
            ${data.map(e => `
                <tr>
                <td><b>${e.encuestado.nombre}</b></td>
                <td>${e.encuestado.departamento}</td>
                <td>${e.encuestado.edad}</td>
                <td><span class="badge badge-azul">E${e.encuestado.estrato}</span></td>
                <td><span class="badge badge-gris">${e.encuestado.nivel_educativo || "—"}</span></td>
                <td>${e.fuente || "—"}</td>
                <td>
                    <span 
                    style="font-size:11px;color:var(--primario);cursor:pointer;text-decoration:underline" 
                    onclick="copiarId('${e.id}')"
                    title="Clic para copiar y buscar"
                    >
                    ${e.id.substring(0,8)}...
                    </span>
                </td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="eliminarEncuesta('${e.id}')">🗑</button>
                </td>
                </tr>`).join("")}
            </tbody>
        </table>`;
    } catch(e) {
        div.innerHTML = `<div class="empty">Error cargando encuestas.</div>`;
    }
    }

    function copiarId(id) {
    document.getElementById("buscar-id").value = id;
    buscarPorId();
  window.scrollTo({top: 0, behavior: 'smooth'});

}

// Cargar al iniciar
cargarEstadisticas();
cargarEncuestas();
cargarEstadisticasRespuestas();
</script>
</body>
</html>
"""