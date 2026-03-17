"""
tests/test_endpoints.py
Tests de integración para los endpoints de la API.
Ejecutar: pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ── Payload base reutilizable ─────────────────────────────────────────────
ENCUESTA_VALIDA = {
    "encuestado": {
        "nombre": "Carlos Ramírez",
        "edad": 45,
        "sexo": "M",
        "estrato": 2,
        "departamento": "Valle del Cauca",
        "area": "cabecera",
        "nivel_educativo": "secundaria",
        "afiliado_salud": True
    },
    "respuestas": [
        {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 3},
        {"pregunta_id": "P02", "tipo_pregunta": "porcentaje", "valor": 65.0},
        {"pregunta_id": "P03", "tipo_pregunta": "binaria", "valor": "si"}
    ],
    "fuente": "GEIH-2024"
}


# ── Tests GET / ───────────────────────────────────────────────────────────
class TestRaiz:

    def test_raiz_retorna_200(self):
        r = client.get("/")
        assert r.status_code == 200

    def test_raiz_contiene_version(self):
        r = client.get("/")
        assert r.json()["version"] == "1.0.0"


# ── Tests POST /encuestas/ ────────────────────────────────────────────────
class TestCrearEncuesta:

    def test_crear_encuesta_valida_retorna_201(self):
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        assert r.status_code == 201

    def test_crear_encuesta_retorna_id(self):
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        assert "id" in r.json()

    def test_crear_encuesta_retorna_timestamp(self):
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        assert "registrado_en" in r.json()

    def test_edad_invalida_retorna_422(self):
        payload = dict(ENCUESTA_VALIDA)
        payload["encuestado"] = {**ENCUESTA_VALIDA["encuestado"], "edad": 150}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422

    def test_estrato_invalido_retorna_422(self):
        payload = dict(ENCUESTA_VALIDA)
        payload["encuestado"] = {**ENCUESTA_VALIDA["encuestado"], "estrato": 9}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422

    def test_departamento_invalido_retorna_422(self):
        payload = dict(ENCUESTA_VALIDA)
        payload["encuestado"] = {**ENCUESTA_VALIDA["encuestado"], "departamento": "Lemuria"}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422

    def test_422_retorna_estructura_personalizada(self):
        payload = dict(ENCUESTA_VALIDA)
        payload["encuestado"] = {**ENCUESTA_VALIDA["encuestado"], "estrato": 9}
        r = client.post("/encuestas/", json=payload)
        data = r.json()
        assert "errores" in data
        assert "mensaje" in data
        assert "ayuda" in data


# ── Tests GET /encuestas/ ─────────────────────────────────────────────────
class TestListarEncuestas:

    def test_listar_retorna_200(self):
        r = client.get("/encuestas/")
        assert r.status_code == 200

    def test_listar_retorna_lista(self):
        r = client.get("/encuestas/")
        assert isinstance(r.json(), list)


# ── Tests GET /encuestas/{id} ─────────────────────────────────────────────
class TestObtenerEncuesta:

    def test_obtener_encuesta_existente(self):
        # Crear una encuesta primero
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        encuesta_id = r.json()["id"]
        # Obtenerla por ID
        r2 = client.get(f"/encuestas/{encuesta_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == encuesta_id

    def test_obtener_id_inexistente_retorna_404(self):
        r = client.get("/encuestas/id-que-no-existe")
        assert r.status_code == 404


# ── Tests DELETE /encuestas/{id} ──────────────────────────────────────────
class TestEliminarEncuesta:

    def test_eliminar_encuesta_existente_retorna_204(self):
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        encuesta_id = r.json()["id"]
        r2 = client.delete(f"/encuestas/{encuesta_id}")
        assert r2.status_code == 204

    def test_eliminar_id_inexistente_retorna_404(self):
        r = client.delete("/encuestas/id-que-no-existe")
        assert r.status_code == 404


# ── Tests GET /encuestas/estadisticas/ ───────────────────────────────────
class TestEstadisticas:

    def test_estadisticas_retorna_200(self):
        r = client.get("/encuestas/estadisticas/")
        assert r.status_code == 200

    def test_estadisticas_contiene_campos(self):
        r = client.get("/encuestas/estadisticas/")
        data = r.json()
        assert "total_encuestas" in data
        assert "promedio_edad" in data
        assert "distribucion_estrato" in data
