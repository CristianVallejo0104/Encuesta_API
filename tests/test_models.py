"""
tests/test_models.py
Tests unitarios para los modelos Pydantic.
Ejecutar: pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError
from models import Encuestado, RespuestaEncuesta, EncuestaCompleta


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture
def encuestado_valido():
    return {
        "nombre": "María García",
        "edad": 34,
        "sexo": "F",
        "estrato": 3,
        "departamento": "Antioquia",
        "area": "cabecera",
        "nivel_educativo": "universitario",
        "afiliado_salud": True
    }

@pytest.fixture
def respuesta_valida():
    return {
        "pregunta_id": "P01",
        "tipo_pregunta": "likert",
        "valor": 4
    }


# ── Tests Encuestado ──────────────────────────────────────────────────────
class TestEncuestado:

    def test_encuestado_valido(self, encuestado_valido):
        enc = Encuestado(**encuestado_valido)
        assert enc.nombre == "María García"
        assert enc.edad == 34

    def test_edad_mayor_120(self, encuestado_valido):
        encuestado_valido["edad"] = 121
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_edad_negativa(self, encuestado_valido):
        encuestado_valido["edad"] = -1
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_estrato_invalido(self, encuestado_valido):
        encuestado_valido["estrato"] = 7
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_estrato_cero(self, encuestado_valido):
        encuestado_valido["estrato"] = 0
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_departamento_invalido(self, encuestado_valido):
        encuestado_valido["departamento"] = "Lemuria"
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_departamento_normaliza_mayusculas(self, encuestado_valido):
        encuestado_valido["departamento"] = "ANTIOQUIA"
        enc = Encuestado(**encuestado_valido)
        assert enc.departamento == "Antioquia"

    def test_sexo_invalido(self, encuestado_valido):
        encuestado_valido["sexo"] = "X"
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_sexo_minuscula_aceptado(self, encuestado_valido):
        encuestado_valido["sexo"] = "f"
        enc = Encuestado(**encuestado_valido)
        assert enc.sexo == "F"

    def test_nivel_educativo_invalido(self, encuestado_valido):
        encuestado_valido["nivel_educativo"] = "doctorado"
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_area_invalida(self, encuestado_valido):
        encuestado_valido["area"] = "urbano"
        with pytest.raises(ValidationError):
            Encuestado(**encuestado_valido)

    def test_area_valida_rural(self, encuestado_valido):
        encuestado_valido["area"] = "rural_disperso"
        enc = Encuestado(**encuestado_valido)
        assert enc.area == "rural_disperso"


# ── Tests RespuestaEncuesta ───────────────────────────────────────────────
class TestRespuestaEncuesta:

    def test_likert_valido(self, respuesta_valida):
        r = RespuestaEncuesta(**respuesta_valida)
        assert r.valor == 4

    def test_likert_fuera_rango(self):
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="likert", valor=6)

    def test_porcentaje_valido(self):
        r = RespuestaEncuesta(pregunta_id="P02", tipo_pregunta="porcentaje", valor=75.5)
        assert r.valor == 75.5

    def test_porcentaje_mayor_100(self):
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P02", tipo_pregunta="porcentaje", valor=101)

    def test_binaria_valida(self):
        r = RespuestaEncuesta(pregunta_id="P03", tipo_pregunta="binaria", valor="si")
        assert r.valor == "si"

    def test_binaria_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P03", tipo_pregunta="binaria", valor="quizas")

    def test_tipo_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="multiple", valor=2)

    def test_pregunta_id_formato_incorrecto(self):
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="X1", tipo_pregunta="likert", valor=3)


# ── Tests EncuestaCompleta ────────────────────────────────────────────────
class TestEncuestaCompleta:

    def test_encuesta_valida(self, encuestado_valido, respuesta_valida):
        enc = EncuestaCompleta(
            encuestado=encuestado_valido,
            respuestas=[respuesta_valida]
        )
        assert enc.encuestado.nombre == "María García"
        assert len(enc.respuestas) == 1

    def test_sin_respuestas_rechazada(self, encuestado_valido):
        with pytest.raises(ValidationError):
            EncuestaCompleta(encuestado=encuestado_valido, respuestas=[])

    def test_preguntas_duplicadas_rechazadas(self, encuestado_valido, respuesta_valida):
        with pytest.raises(ValidationError):
            EncuestaCompleta(
                encuestado=encuestado_valido,
                respuestas=[respuesta_valida, respuesta_valida]
            )