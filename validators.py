"""
Validadores auxiliares para la API de Encuestas Poblacionales.
Fuente: DANE - División Político-Administrativa DIVIPOLA 2024
"""

DEPARTAMENTOS_COLOMBIA= ["Amazonas", "Antioquia", "Arauca", "Atlántico", "Bolívar",
    "Boyacá", "Caldas", "Caquetá", "Casanare", "Cauca", "Cesar",
    "Chocó", "Córdoba", "Cundinamarca", "Guainía", "Guaviare",
    "Huila", "La Guajira", "Magdalena", "Meta", "Nariño",
    "Norte de Santander", "Putumayo", "Quindío", "Risaralda",
    "San Andrés y Providencia", "Santander", "Sucre", "Tolima",
    "Valle del Cauca", "Vaupés", "Vichada", "Bogotá D.C."]

ESTRATOS_VALIDOS=[1,2,3,4,5,6]

NIVELES_EDUCATIVOS=["ninguno", "primaria", "secundaria",
    "tecnico", "tecnologico", "universitario", "posgrado"]

TIPOS_PREGUNTA=["likert", "porcentaje", "binaria", "texto"]

# ── Rangos estadísticos ───────────────────────────────────────────────────
EDAD_MIN = 0
EDAD_MAX = 120
LIKERT_MIN = 1
LIKERT_MAX = 5
PORCENTAJE_MIN = 0.0
PORCENTAJE_MAX = 100.0

def validar_departamento(valor: str) -> str:
    """
    Normaliza y valida el nombre del departamento contra
    la lista oficial DIVIPOLA del DANE.
    """
    valor_limpio = valor.strip().title()
    for dep in DEPARTAMENTOS_COLOMBIA:
        if dep.lower() == valor_limpio.lower():
            return dep
    raise ValueError(
        f"'{valor}' no es un departamento válido de Colombia. "
        f"Consulte la lista DIVIPOLA-DANE."
    )


def validar_nivel_educativo(valor: str) -> str:
    """Valida el nivel educativo contra la nomenclatura GEIH-DANE."""
    v = valor.strip().lower()
    if v not in NIVELES_EDUCATIVOS:
        raise ValueError(
            f"Nivel educativo '{valor}' no válido. "
            f"Opciones: {NIVELES_EDUCATIVOS}"
        )
    return v
