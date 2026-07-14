from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


POSITIONS_FILE = Path("top_50_active_positions.csv")
OUTPUT_FILE = Path("sports_consensus_v2.csv")


def numero(valor: object) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def peso_ranking(ranking: float) -> float:
    """Da mayor importancia a los traders mejor clasificados."""

    if ranking <= 5:
        return 1.00

    if ranking <= 10:
        return 0.90

    if ranking <= 20:
        return 0.75

    if ranking <= 35:
        return 0.55

    return 0.40


def tipo_mercado(titulo: str) -> str:
    texto = str(titulo).lower()

    marcadores = [
        "exact score",
        "correct score",
        "marcador exacto",
    ]

    jugadores = [
        "golden ball",
        "top goalscorer",
        "first goalscorer",
        "anytime scorer",
        "player to score",
    ]

    if any(palabra in texto for palabra in marcadores):
        return "Marcador exacto / posible cobertura"

    if any(palabra in texto for palabra in jugadores):
        return "Mercado especial de jugador"

    return "Direccional"


def nombre_corto(usuario: object, wallet: object) -> str:
    usuario_texto = str(usuario).strip()
    wallet_texto = str(wallet).strip()

    if (
        usuario_texto
        and usuario_texto.lower() not in {"nan", "sin nombre", "none"}
        and not usuario_texto.startswith("0x")
    ):
        return usuario_texto

    if wallet_texto.startswith("0x") and len(wallet_texto) > 14:
        return f"Wallet {wallet_texto[:6]}...{wallet_texto[-4:]}"

    return "Trader sin nombre"


def cargar_posiciones() -> pd.DataFrame:
    if not POSITIONS_FILE.exists():
        raise FileNotFoundError(
            "No se encontró top_50_active_positions.csv.\n"
            "Primero ejecuta: python positions.py"
        )

    tabla = pd.read_csv(POSITIONS_FILE)

    columnas_requeridas = {
        "Ranking",
        "Usuario",
        "Wallet",
        "Mercado",
        "Lado",
        "Valor_Actual_USD",
        "Precio_Entrada",
        "Precio_Actual",
        "Condition_ID",
    }

    faltantes = columnas_requeridas - set(tabla.columns)

    if faltantes:
        raise ValueError(
            "Faltan columnas en el archivo de posiciones: "
            + ", ".join(sorted(faltantes))
        )

    columnas_numericas = [
        "Ranking",
        "Valor_Actual_USD",
        "Precio_Entrada",
        "Precio_Actual",
    ]

    for columna in columnas_numericas:
        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0)

    tabla["Trader_Corto"] = tabla.apply(
        lambda fila: nombre_corto(
            fila["Usuario"],
            fila["Wallet"],
        ),
        axis=1,
    )

    tabla["Peso_Ranking"] = tabla["Ranking"].map(peso_ranking)

    # Raíz cuadrada para evitar que una sola posición enorme domine todo.
    tabla["Peso_Capital"] = tabla["Valor_Actual_USD"].clip(lower=0).pow(0.5)

    tabla["Peso_Whale"] = (
        tabla["Peso_Ranking"] * tabla["Peso_Capital"]
    )

    tabla["Tipo"] = tabla["Mercado"].map(tipo_mercado)

    return tabla


def calcular_wci(
    traders: int,
    capital: float,
    calidad_ranking: float,
    consenso_neto: float,
    tipo: str,
) -> float:
    """
    WCI de 0 a 100.

    No representa probabilidad de ganar.
    """

    # Hasta 30 puntos por cantidad de traders.
    puntos_traders = min(traders / 8, 1) * 30

    # Hasta 20 puntos por capital visible.
    # La escala logarítmica reduce el dominio de posiciones gigantes.
    if capital > 0:
        puntos_capital = min(math.log10(capital + 1) / 7, 1) * 20
    else:
        puntos_capital = 0

    # Hasta 20 puntos por calidad promedio del ranking.
    puntos_ranking = max(0, min(calidad_ranking, 1)) * 20

    # Hasta 30 puntos por predominio frente al lado contrario.
    puntos_consenso = max(0, min(consenso_neto, 1)) * 30

    puntuacion = (
        puntos_traders
        + puntos_capital
        + puntos_ranking
        + puntos_consenso
    )

    if tipo == "Marcador exacto / posible cobertura":
        puntuacion -= 18

    if tipo == "Mercado especial de jugador":
        puntuacion -= 8

        puntuacion = max(0, min(puntuacion, 100))

    if traders <= 1:
        puntuacion = min(puntuacion, 45)
    elif traders == 2:
        puntuacion = min(puntuacion, 64)
    elif traders == 3:
        puntuacion = min(puntuacion, 78)
    elif traders == 4:
        puntuacion = min(puntuacion, 88)

    return round(puntuacion, 1)


def crear_consenso(tabla: pd.DataFrame) -> pd.DataFrame:
    if tabla.empty:
        return pd.DataFrame()

    agrupado = (
        tabla.groupby(
            [
                "Condition_ID",
                "Mercado",
                "Lado",
                "Tipo",
            ],
            dropna=False,
        )
        .agg(
            Traders_Coincidentes=("Wallet", "nunique"),
            Capital_Visible_USD=("Valor_Actual_USD", "sum"),
            Precio_Entrada_Promedio=("Precio_Entrada", "mean"),
            Precio_Actual_Promedio=("Precio_Actual", "mean"),
            Ranking_Mejor=("Ranking", "min"),
            Calidad_Ranking=("Peso_Ranking", "mean"),
            Peso_Lado=("Peso_Whale", "sum"),
            Traders=(
                "Trader_Corto",
                lambda valores: ", ".join(
                    sorted(set(str(valor) for valor in valores))
                ),
            ),
        )
        .reset_index()
    )

    # Suma todos los lados del mismo mercado.
    totales_mercado = (
        agrupado.groupby("Condition_ID", dropna=False)
        .agg(
            Peso_Total_Mercado=("Peso_Lado", "sum"),
            Capital_Total_Mercado=("Capital_Visible_USD", "sum"),
            Traders_Totales_Mercado=("Traders_Coincidentes", "sum"),
        )
        .reset_index()
    )

    resultado = agrupado.merge(
        totales_mercado,
        on="Condition_ID",
        how="left",
    )

    resultado["Consenso_Neto"] = resultado.apply(
        lambda fila: (
            fila["Peso_Lado"] / fila["Peso_Total_Mercado"]
            if fila["Peso_Total_Mercado"] > 0
            else 0
        ),
        axis=1,
    )

    resultado["Oposicion_Peso"] = (
        resultado["Peso_Total_Mercado"] - resultado["Peso_Lado"]
    )

    resultado["Oposicion_Capital_USD"] = (
        resultado["Capital_Total_Mercado"]
        - resultado["Capital_Visible_USD"]
    )

    resultado["WCI"] = resultado.apply(
        lambda fila: calcular_wci(
            traders=int(fila["Traders_Coincidentes"]),
            capital=numero(fila["Capital_Visible_USD"]),
            calidad_ranking=numero(fila["Calidad_Ranking"]),
            consenso_neto=numero(fila["Consenso_Neto"]),
            tipo=str(fila["Tipo"]),
        ),
        axis=1,
    )

    resultado["Consenso_Porcentaje"] = (
        resultado["Consenso_Neto"] * 100
    ).round(1)

    resultado["Advertencia"] = resultado.apply(
        lambda fila: (
            "Revisar reglas: un pick NO puede incluir empate "
            "o una resolución distinta a clasificación."
            if str(fila["Lado"]).lower() == "no"
            else ""
        ),
        axis=1,
    )

    resultado = resultado.sort_values(
        by=[
            "WCI",
            "Traders_Coincidentes",
            "Capital_Visible_USD",
        ],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return resultado


def mostrar_resumen(resultado: pd.DataFrame) -> None:
    print("\n" + "=" * 120)
    print("WHALESPORTS AI — CONSENSO V2")
    print("=" * 120)

    señales = resultado[
        (resultado["Traders_Coincidentes"] >= 2)
        & (resultado["Tipo"] == "Direccional")
    ].head(20)

    if señales.empty:
        print("No se encontraron coincidencias direccionales.")
        return

    columnas = [
        "Mercado",
        "Lado",
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Consenso_Porcentaje",
        "Oposicion_Capital_USD",
        "WCI",
        "Ranking_Mejor",
    ]

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_colwidth", 55)

    print(señales[columnas].to_string(index=False))

    print("\nIMPORTANTE:")
    print("- WCI no es probabilidad de ganar.")
    print("- Consenso_Porcentaje compara el peso visible de ambos lados.")
    print("- Los mercados NO deben revisarse según sus reglas exactas.")


def main() -> None:
    print("Leyendo posiciones activas...")

    posiciones = cargar_posiciones()

    print(f"Posiciones cargadas: {len(posiciones)}")

    resultado = crear_consenso(posiciones)

    resultado.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    mostrar_resumen(resultado)

    print(f"\nArchivo creado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()