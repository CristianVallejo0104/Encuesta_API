"""
Modelos Pydantic para la API de Encuestas Poblacionales GEIH-DANE 2024.

Jerarquía:
    Encuestado ──────────────────────────────┐
    RespuestaEncuesta (List) ────────────────┤──► EncuestaCompleta
                                             │
                                        EncuestaDB (+ id + timestamp)
"""
from __future__ import annotations 
import uuid 
from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from validators import (
    DEPARTAMENTOS_COLOMBIA,
    ESTRATOS_VALIDOS,
    NIVELES_EDUCATIVOS,
    TIPOS_PREGUNTA,
    AREAS_VALIDAS,
    EDAD_MIN, EDAD_MAX,
    LIKERT_MIN, LIKERT_MAX,
    validar_departamento,
    validar_nivel_educativo,
)

# MODELO 1: Encuestado — datos demográficos reales GEIH-DANE

class Encuestado(BaseModel):
    """
    Datos demográficos del respondente.
    Variables alineadas con el módulo de Características
    Generales de la GEIH Diciembre 2024 - DANE.
    """

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "María Rodríguez",
                "edad": 34,
                "sexo": "F",
                "estrato": 3,
                "departamento": "Antioquia",
                "area": "cabecera",
                "nivel_educativo": "universitario",
                "afiliado_salud": True
            }
        }
    }

    nombre: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Nombre completo del encuestado."
    )
    edad: int = Field(
        ...,
        ge=EDAD_MIN,
        le=EDAD_MAX,
        description="Edad en años cumplidos (0-120). Variable P6040 GEIH."
    )
    sexo: str = Field(
        ...,
        description="Sexo del encuestado: 'M' o 'F'. Variable P3271 GEIH."
    )
    estrato: int = Field(
        ...,
        description="Estrato socioeconómico DANE (1-6). Variable P4030S1A1 GEIH."
    )
    departamento: str = Field(
        ...,
        description="Departamento de residencia. Lista oficial DIVIPOLA-DANE."
    )
    area: str = Field(
        default="cabecera",
        description="Área geográfica DANE: 'cabecera' o 'rural_disperso'. Variable CLASE GEIH."
    )
    nivel_educativo: Optional[str] = Field(
        default=None,
        description="Nivel educativo. Variable P3042 GEIH."
    )
    afiliado_salud: Optional[bool] = Field(
        default=None,
        description="¿Afiliado a seguridad social en salud? Variable P6090 GEIH."
    )

    # ── mode='before': se ejecuta ANTES de que Pydantic convierta el tipo ──
    # Útil para limpiar strings antes de validar longitud o contenido
    @field_validator("nombre", mode="before")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        """
        mode='before': normaliza el nombre antes de validar
        longitud mínima y máxima.
        """
        if isinstance(v, str):
            return v.strip().title()
        return v

    @field_validator("departamento", mode="before")
    @classmethod
    def validar_dep(cls, v: str) -> str:
        """
        mode='before': normaliza y valida contra DIVIPOLA
        antes de cualquier otra verificación.
        """
        return validar_departamento(v)

    @field_validator("sexo", mode="before")
    @classmethod
    def validar_sexo(cls, v: str) -> str:
        """mode='before': convierte a mayúscula antes de validar."""
        v_up = v.strip().upper()
        if v_up not in ("M", "F"):
            raise ValueError(
                "El campo 'sexo' acepta únicamente 'M' o 'F'."
            )
        return v_up

    @field_validator("area", mode="before")
    @classmethod
    def validar_area(cls, v: str) -> str:
        v_c = v.strip().lower()
        if v_c not in AREAS_VALIDAS:
            raise ValueError(
                f"'area' debe ser uno de: {AREAS_VALIDAS}."
            )
        return v_c

    @field_validator("nivel_educativo", mode="before")
    @classmethod
    def validar_nivel(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return validar_nivel_educativo(v)

    # ── mode='after': se ejecuta DESPUÉS de la conversión de tipos ─────────
    # Aquí ya tenemos garantía de que v es del tipo correcto
    @field_validator("estrato", mode="after")
    @classmethod
    def validar_estrato(cls, v: int) -> int:
        """
        mode='after': verificamos el rango DANE (1-6)
        después de confirmar que v es int.
        """
        if v not in ESTRATOS_VALIDOS:
            raise ValueError(
                f"Estrato debe ser entre 1 y 6 (clasificación DANE). "
                f"Recibido: {v}."
            )
        return v


# MODELO 2: RespuestaEncuesta — respuesta individual a una pregunta

class RespuestaEncuesta(BaseModel):
    """
    Respuesta de un encuestado a una pregunta específica.
    Soporta tipos: likert (1-5), porcentaje (0-100),
    binaria (si/no) y texto libre.
    """

    model_config = {
        "json_schema_extra": {
            "example": {
                "pregunta_id": "P01",
                "enunciado": "¿Satisfacción con servicios públicos?",
                "tipo_pregunta": "likert",
                "valor": 4,
                "observacion": "El servicio de agua es irregular."
            }
        }
    }

    pregunta_id: str = Field(
        ...,
        pattern=r"^P\d{2,3}$",
        description="ID de la pregunta. Formato: P01, P02, ..., P999."
    )
    enunciado: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Texto de la pregunta (opcional)."
    )
    tipo_pregunta: str = Field(
        ...,
        description=f"Tipo: {TIPOS_PREGUNTA}."
    )
    # Union[int, float, str]: el tipo depende del tipo de pregunta
    valor: Union[int, float, str] = Field(
        ...,
        description="Valor de la respuesta según el tipo de pregunta."
    )
    observacion: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Comentario libre del encuestado."
    )

    @field_validator("tipo_pregunta", mode="before")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        v_c = v.strip().lower()
        if v_c not in TIPOS_PREGUNTA:
            raise ValueError(
                f"Tipo '{v}' no válido. Opciones: {TIPOS_PREGUNTA}."
            )
        return v_c

    @model_validator(mode="after")
    def validar_valor_segun_tipo(self) -> "RespuestaEncuesta":
        """
        Validador cross-field: verifica que el valor sea
        coherente con el tipo de pregunta declarado.
        Se ejecuta después de validar todos los campos individuales.
        """
        tipo = self.tipo_pregunta
        valor = self.valor

        if tipo == "likert":
            if not isinstance(valor, (int, float)) or not (LIKERT_MIN <= int(valor) <= LIKERT_MAX):
                raise ValueError(
                    f"Likert requiere entero entre {LIKERT_MIN} y {LIKERT_MAX}. "
                    f"Recibido: {valor}."
                )
        elif tipo == "porcentaje":
            if not isinstance(valor, (int, float)) or not (0.0 <= float(valor) <= 100.0):
                raise ValueError(
                    f"Porcentaje debe estar entre 0.0 y 100.0. "
                    f"Recibido: {valor}."
                )
        elif tipo == "binaria":
            if str(valor).strip().lower() not in {"si", "sí", "no", "1", "0"}:
                raise ValueError(
                    "Binaria acepta: 'si', 'no', '1' o '0'."
                )
        return self

# MODELO 3: EncuestaCompleta — contenedor principal (entrada de la API)   

class EncuestaCompleta(BaseModel):
    """
    Modelo contenedor: anida un Encuestado + List[RespuestaEncuesta].
    Actúa como 'aduana transaccional': si cualquier campo
    falla, el registro no entra al repositorio de análisis.
    """

    model_config = {
        "json_schema_extra": {
            "example": {
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
                    {
                        "pregunta_id": "P01",
                        "enunciado": "Satisfacción con servicios públicos",
                        "tipo_pregunta": "likert",
                        "valor": 3
                    },
                    {
                        "pregunta_id": "P02",
                        "tipo_pregunta": "porcentaje",
                        "valor": 65.0,
                        "observacion": "% ingreso en alimentación"
                    },
                    {
                        "pregunta_id": "P03",
                        "tipo_pregunta": "binaria",
                        "valor": "si"
                    }
                ],
                "fuente": "GEIH-2024"
            }
        }
    }

    encuestado: Encuestado = Field(
        ...,
        description="Datos demográficos del respondente."
    )
    respuestas: List[RespuestaEncuesta] = Field(
        ...,
        min_length=1,
        description="Lista de respuestas. Mínimo una requerida."
    )
    fuente: Optional[str] = Field(
        default="GEIH-2024",
        max_length=100,
        description="Origen del registro: GEIH-2024, Manual, etc."
    )

    @field_validator("respuestas", mode="after")
    @classmethod
    def sin_preguntas_duplicadas(cls, v: List[RespuestaEncuesta]) -> List[RespuestaEncuesta]:
        ids = [r.pregunta_id for r in v]
        duplicados = {x for x in ids if ids.count(x) > 1}
        if duplicados:
            raise ValueError(
                f"Preguntas duplicadas: {sorted(duplicados)}. "
                f"Cada pregunta debe aparecer una sola vez."
            )
        return v


# MODELO DB: EncuestaDB — versión almacenada (añade id + timestamp)

class EncuestaDB(EncuestaCompleta):
    """Versión persistida: incluye UUID y timestamp de registro."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID generado automáticamente."
    )
    registrado_en: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora de ingreso al sistema."
    )

# MODELOS DE RESPUESTA DE LA API

class EstadisticasResponse(BaseModel):
    """Respuesta del endpoint GET /encuestas/estadisticas/"""

    total_encuestas: int
    promedio_edad: float
    mediana_edad: float
    distribucion_estrato: dict
    distribucion_departamento: dict
    distribucion_sexo: dict
    nivel_educativo: dict
    afiliacion_salud: dict
    promedio_respuestas_por_encuesta: float


class MensajeResponse(BaseModel):
    """Respuesta simple de confirmación."""
    mensaje: str
    id: Optional[str] = None