import pandas as pd
import os

# ── Rutas ──────────────────────────────────────────────────────────────────
RUTA_CSV = os.path.join("datos", "CSV")



ARCHIVO_PERSONAS = os.path.join(
    RUTA_CSV,
    "Características generales, seguridad social en salud y educación.CSV"
)
ARCHIVO_HOGAR = os.path.join(RUTA_CSV, "Datos del hogar y la vivienda.CSV")

# ── Leer archivos ──────────────────────────────────────────────────────────
print("Leyendo archivos...")

df_personas = pd.read_csv(ARCHIVO_PERSONAS, sep=";", encoding="latin-1", low_memory=False)
df_hogar    = pd.read_csv(ARCHIVO_HOGAR,    sep=";", encoding="latin-1", low_memory=False)

print(f"Personas : {df_personas.shape}")
print(f"Hogar    : {df_hogar.shape}")
print("\nColumnas hogar:")
print(df_hogar.columns.tolist())



print("=== PERSONAS ===")
print(df_personas[['DIRECTORIO', 'DPTO', 'P3271', 'P6040', 'CLASE', 'P3042', 'P6090']].head(5))

print("\n=== Valores únicos DPTO ===")
print(sorted(df_personas['DPTO'].dropna().unique()))

print("\n=== Valores únicos P3271 (sexo) ===")
print(df_personas['P3271'].value_counts())

print("\n=== Valores únicos P3042 (nivel educativo) ===")
print(df_personas['P3042'].value_counts().sort_index())

print("\n=== HOGAR — estrato P4030S1A1 ===")
print(df_hogar['P4030S1A1'].value_counts().sort_index())



DPTO_NOMBRES = {
    5: "Antioquia", 8: "Atlántico", 11: "Bogotá D.C.", 13: "Bolívar",
    15: "Boyacá", 17: "Caldas", 18: "Caquetá", 19: "Cauca", 20: "Cesar",
    23: "Córdoba", 25: "Cundinamarca", 27: "Chocó", 41: "Huila",
    44: "La Guajira", 47: "Magdalena", 50: "Meta", 52: "Nariño",
    54: "Norte de Santander", 63: "Quindío", 66: "Risaralda",
    68: "Santander", 70: "Sucre", 73: "Tolima", 76: "Valle del Cauca",
    81: "Arauca", 85: "Casanare", 86: "Putumayo",
    88: "San Andrés y Providencia", 91: "Amazonas", 94: "Guainía",
    95: "Guaviare", 97: "Vaupés", 99: "Vichada"
}

# P3042 → nivel educativo simplificado para la API
NIVEL_EDU = {
    1.0: "ninguno",
    2.0: "ninguno",       # preescolar → ninguno
    3.0: "primaria",
    4.0: "secundaria",
    5.0: "secundaria",    # media/bachillerato
    6.0: "tecnico",       # normalista
    7.0: "tecnico",
    8.0: "tecnico",
    9.0: "tecnologico",
    10.0: "universitario",
    11.0: "posgrado",
    12.0: "posgrado",
    13.0: "posgrado",
    99.0: None
}

SEXO = {1: "M", 2: "F"}
AREA = {1: "cabecera", 2: "rural_disperso"}

# ── Seleccionar columnas útiles de cada archivo ────────────────────────────
personas = df_personas[[
    'DIRECTORIO', 'DPTO', 'P3271', 'P6040', 'CLASE', 'P3042', 'P6090'
]].copy()

hogar = df_hogar[['DIRECTORIO', 'P4030S1A1']].copy()

# ── Cruzar por DIRECTORIO ──────────────────────────────────────────────────
df = personas.merge(hogar, on='DIRECTORIO', how='left')

print(f"Filas después del cruce: {df.shape}")
print(f"Nulos en estrato: {df['P4030S1A1'].isna().sum()}")
print(df.head(3))



# ── Aplicar mapas de decodificación ───────────────────────────────────────
df['departamento']     = df['DPTO'].map(DPTO_NOMBRES)
df['sexo']             = df['P3271'].map(SEXO)
df['edad']             = df['P6040']
df['area']             = df['CLASE'].map(AREA)
df['nivel_educativo']  = df['P3042'].map(NIVEL_EDU)
df['estrato']          = df['P4030S1A1']
df['afiliado_salud']   = df['P6090']  # 1=sí, 2=no → pregunta de encuesta

# ── Filtrar filas válidas para la API ─────────────────────────────────────
df_limpio = df[
    df['departamento'].notna() &
    df['sexo'].notna() &
    df['edad'].between(0, 120) &
    df['estrato'].isin([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) &
    df['nivel_educativo'].notna()
].copy()

# Estrato como entero
df_limpio['estrato'] = df_limpio['estrato'].astype(int)

# ── Quedarnos solo con las columnas finales ────────────────────────────────
df_final = df_limpio[[
    'DIRECTORIO', 'departamento', 'sexo', 'edad',
    'area', 'nivel_educativo', 'estrato', 'afiliado_salud'
]].reset_index(drop=True)

print(f"Filas después de limpieza: {len(df_final)}")
print(f"\nDistribución estrato:\n{df_final['estrato'].value_counts().sort_index()}")
print(f"\nDistribución sexo:\n{df_final['sexo'].value_counts()}")
print(f"\nMuestra:\n{df_final.head(5)}")


# ── Guardar dataset limpio ─────────────────────────────────────────────────
RUTA_SALIDA = os.path.join("datos", "geih_diciembre_2024_limpio.csv")

df_final.to_csv(RUTA_SALIDA, index=False, encoding="utf-8")

print(f"✔ Dataset guardado en: {RUTA_SALIDA}")
print(f"  Registros : {len(df_final):,}")
print(f"  Columnas  : {list(df_final.columns)}")
