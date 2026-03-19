"""

Lee el dataset GEIH 2024 desde CSV con pandas,
envía registros a la API y genera un reporte estadístico.

Uso:
    python cliente_csv.py
    (La API debe estar corriendo: uvicorn main:app --reload)
"""

import requests
import pandas as pd
from datetime import datetime

API = "https://encuesta-api-vhq1.onrender.com"
CSV_PATH = "datos/geih_diciembre_2024_limpio.csv"
MAX_REGISTROS = 20  # Cambiar a None para cargar todos


def construir_payload(fila: pd.Series) -> dict:
    """Transforma una fila del CSV en el JSON esperado por la API."""
    return {
        "encuestado": {
            "nombre": f"Encuestado GEIH {fila['DIRECTORIO']}",
            "edad": int(fila["edad"]),
            "sexo": fila["sexo"],
            "estrato": int(fila["estrato"]),
            "departamento": fila["departamento"],
            "area": fila["area"],
            "nivel_educativo": fila["nivel_educativo"],
            "afiliado_salud": bool(fila["afiliado_salud"] == 1),
        },
        "respuestas": [
            {
                "pregunta_id": "P01",
                "enunciado": "¿Afiliado a seguridad social en salud?",
                "tipo_pregunta": "binaria",
                "valor": "si" if fila["afiliado_salud"] == 1 else "no",
            }
        ],
        "fuente": "GEIH-Diciembre-2024",
    }


def cargar_encuestas(df: pd.DataFrame) -> dict:
    """Envía cada fila del CSV a la API."""
    resultados = {"exitosos": 0, "fallidos": 0, "errores": []}

    for idx, fila in df.iterrows():
        payload = construir_payload(fila)
        try:
            r = requests.post(f"{API}/encuestas/", json=payload, timeout=10)
            if r.status_code == 201:
                resultados["exitosos"] += 1
            else:
                resultados["fallidos"] += 1
                resultados["errores"].append({
                    "fila": idx,
                    "status": r.status_code,
                    "detalle": r.json().get("errores", [])
                })
        except requests.exceptions.ConnectionError:
            print("❌ No se pudo conectar a la API.")
            print("   Asegúrate de correr: uvicorn main:app --reload")
            break

    return resultados


def reporte_estadistico(df: pd.DataFrame):
    """Genera reporte estadístico del dataset con pandas."""
    print("\n" + "=" * 55)
    print("  REPORTE — GEIH Diciembre 2024 (DANE)")
    print(f"  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    print(f"\n  Registros procesados : {len(df):,}")

    print("\n  Edad — estadísticas descriptivas:")
    desc = df["edad"].describe().round(2)
    print(f"    Promedio : {desc['mean']}")
    print(f"    Mediana  : {df['edad'].median()}")
    print(f"    Mínimo   : {desc['min']}")
    print(f"    Máximo   : {desc['max']}")

    print("\n  Distribución por estrato:")
    for est, cnt in df["estrato"].value_counts().sort_index().items():
        barra = "█" * int(cnt / df["estrato"].value_counts().max() * 20)
        print(f"    Estrato {est}: {cnt:4d} {barra}")

    print("\n  Distribución por sexo:")
    for s, cnt in df["sexo"].value_counts().items():
        label = "Masculino" if s == "M" else "Femenino"
        print(f"    {label}: {cnt} ({cnt/len(df)*100:.1f}%)")

    print("\n  Top 5 departamentos:")
    for dep, cnt in df["departamento"].value_counts().head(5).items():
        print(f"    {dep}: {cnt}")

    print("\n  Nivel educativo:")
    for niv, cnt in df["nivel_educativo"].value_counts().items():
        print(f"    {niv}: {cnt} ({cnt/len(df)*100:.1f}%)")
    print()


def consultar_estadisticas_api():
    """Consulta el endpoint de estadísticas de la API."""
    try:
        r = requests.get(f"{API}/encuestas/estadisticas/", timeout=10)
        if r.status_code == 200:
            d = r.json()
            print("  Estadísticas en la API (post-carga):")
            print(f"    Total encuestas  : {d['total_encuestas']}")
            print(f"    Promedio edad    : {d['promedio_edad']}")
            print(f"    Mediana edad     : {d['mediana_edad']}")
            print(f"    Distribuc. sexo  : {d['distribucion_sexo']}")
    except Exception as e:
        print(f"  ⚠ No se pudo consultar: {e}")


def main():
    print("=" * 55)
    print("  Cliente Python — GEIH 2024 → API")
    print("=" * 55)

    # 1. Cargar CSV con pandas
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
        print(f"\n✔ CSV cargado: {len(df):,} registros.")
    except FileNotFoundError:
        print(f"❌ No se encontró: {CSV_PATH}")
        return

    if MAX_REGISTROS:
        df = df.head(MAX_REGISTROS)
        print(f"  Procesando primeros {MAX_REGISTROS} registros.")

    # 2. Reporte estadístico del CSV
    reporte_estadistico(df)

    # 3. Enviar a la API
    print("📤 Enviando encuestas a la API...")
    resultados = cargar_encuestas(df)
    print(f"\n  Exitosos : {resultados['exitosos']}")
    print(f"  Fallidos : {resultados['fallidos']}")

    if resultados["fallidos"] > 0:
        print("\n  Primeros errores:")
        for err in resultados["errores"][:3]:
            print(f"    Fila {err['fila']}: HTTP {err['status']}")

    # 4. Estadísticas de la API
    print("\n📊 Consultando estadísticas de la API...")
    consultar_estadisticas_api()
    print("\n✅ Finalizado.")


if __name__ == "__main__":
    main()