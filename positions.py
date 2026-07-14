from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests


POSITIONS_URL = "https://data-api.polymarket.com/positions"
LEADERBOARD_FILE = Path("top_50_sports_traders.csv")
OUTPUT_POSITIONS_FILE = Path("top_50_active_positions.csv")
OUTPUT_CONSENSUS_FILE = Path("sports_consensus.csv")

MIN_POSITION_VALUE_USD = 100.0
REQUEST_DELAY_SECONDS = 0.15
POSITIONS_LIMIT = 500


def cargar_traders() -> pd.DataFrame:
    """Carga el archivo generado por leaderboard.py."""

    if not LEADERBOARD_FILE.exists():
        raise FileNotFoundError(
            "No se encontró top_50_sports_traders.csv.\n"
            "Primero ejecuta: python leaderboard.py"
        )

    traders = pd.read_csv(LEADERBOARD_FILE)

    columnas_necesarias = {"Ranking", "Usuario", "Wallet"}

    if not columnas_necesarias.issubset(traders.columns):
        raise ValueError(
            "El archivo del leaderboard no contiene las columnas esperadas."
        )

    traders = traders.dropna(subset=["Wallet"]).copy()
    traders["Ranking"] = pd.to_numeric(
        traders["Ranking"],
        errors="coerce",
    )

    return traders


def descargar_posiciones(wallet: str) -> list[dict[str, Any]]:
    """Consulta las posiciones activas públicas de una wallet."""

    parametros = {
        "user": wallet,
        "sizeThreshold": 0,
        "limit": POSITIONS_LIMIT,
        "sortBy": "CURRENT",
        "sortDirection": "DESC",
    }

    respuesta = requests.get(
        POSITIONS_URL,
        params=parametros,
        timeout=30,
    )
    respuesta.raise_for_status()

    datos = respuesta.json()

    if not isinstance(datos, list):
        return []

    return datos


def obtener_numero(
    registro: dict[str, Any],
    *claves: str,
) -> float:
    """Busca una cifra usando distintos nombres posibles."""

    for clave in claves:
        valor = registro.get(clave)

        if valor is None or valor == "":
            continue

        try:
            return float(valor)
        except (TypeError, ValueError):
            continue

    return 0.0


def obtener_texto(
    registro: dict[str, Any],
    *claves: str,
    predeterminado: str = "",
) -> str:
    """Busca texto usando distintos nombres posibles."""

    for clave in claves:
        valor = registro.get(clave)

        if valor is not None and str(valor).strip():
            return str(valor).strip()

    return predeterminado


def convertir_posicion(
    posicion: dict[str, Any],
    ranking: int,
    usuario: str,
    wallet: str,
) -> dict[str, Any]:
    """Convierte una posición de la API a una fila uniforme."""

    titulo = obtener_texto(
        posicion,
        "title",
        "marketTitle",
        "question",
        predeterminado="Mercado sin título",
    )

    lado = obtener_texto(
        posicion,
        "outcome",
        "side",
        predeterminado="Sin lado",
    )

    cantidad = obtener_numero(
        posicion,
        "size",
        "shares",
        "tokens",
    )

    precio_promedio = obtener_numero(
        posicion,
        "avgPrice",
        "averagePrice",
        "price",
    )

    precio_actual = obtener_numero(
        posicion,
        "curPrice",
        "currentPrice",
        "markPrice",
    )

    valor_actual = obtener_numero(
        posicion,
        "currentValue",
        "value",
    )

    if valor_actual <= 0 and cantidad > 0 and precio_actual > 0:
        valor_actual = cantidad * precio_actual

    valor_inicial = obtener_numero(
        posicion,
        "initialValue",
        "costBasis",
    )

    pnl = obtener_numero(
        posicion,
        "cashPnl",
        "pnl",
        "realizedPnl",
    )

    porcentaje_pnl = obtener_numero(
        posicion,
        "percentPnl",
        "pnlPercent",
    )

    condicion = obtener_texto(
        posicion,
        "conditionId",
        predeterminado="",
    )

    slug = obtener_texto(
        posicion,
        "slug",
        "eventSlug",
        predeterminado="",
    )

    token_id = obtener_texto(
        posicion,
        "asset",
        "tokenId",
        predeterminado="",
    )

    return {
        "Ranking": int(ranking),
        "Usuario": usuario,
        "Wallet": wallet,
        "Mercado": titulo,
        "Lado": lado,
        "Cantidad": cantidad,
        "Precio_Entrada": precio_promedio,
        "Precio_Actual": precio_actual,
        "Valor_Inicial_USD": valor_inicial,
        "Valor_Actual_USD": valor_actual,
        "PNL_USD": pnl,
        "PNL_Porcentaje": porcentaje_pnl,
        "Condition_ID": condicion,
        "Token_ID": token_id,
        "Slug": slug,
    }


def descargar_todas_las_posiciones(
    traders: pd.DataFrame,
) -> pd.DataFrame:
    """Descarga las posiciones de todos los traders."""

    registros: list[dict[str, Any]] = []
    total = len(traders)

    for indice, trader in traders.iterrows():
        ranking = int(trader["Ranking"])
        usuario = str(trader["Usuario"])
        wallet = str(trader["Wallet"])

        print(
            f"[{indice + 1}/{total}] "
            f"Consultando #{ranking} {usuario}..."
        )

        try:
            posiciones = descargar_posiciones(wallet)
        except requests.RequestException as error:
            print(f"  Error al consultar esta wallet: {error}")
            continue

        posiciones_validas = 0

        for posicion in posiciones:
            fila = convertir_posicion(
                posicion=posicion,
                ranking=ranking,
                usuario=usuario,
                wallet=wallet,
            )

            if fila["Valor_Actual_USD"] < MIN_POSITION_VALUE_USD:
                continue

            registros.append(fila)
            posiciones_validas += 1

        print(f"  Posiciones relevantes: {posiciones_validas}")

        time.sleep(REQUEST_DELAY_SECONDS)

    return pd.DataFrame(registros)


def calcular_peso_ranking(ranking: int) -> float:
    """Da más importancia a los traders mejor clasificados."""

    if ranking <= 10:
        return 5.0

    if ranking <= 25:
        return 3.0

    return 1.0


def detectar_tipo_mercado(titulo: str) -> str:
    """Clasifica mercados que podrían ser coberturas o apuestas específicas."""

    texto = titulo.lower()

    palabras_marcador = [
        "exact score",
        "correct score",
        "marcador exacto",
    ]

    palabras_especiales = [
        "golden ball",
        "top goalscorer",
        "first scorer",
        "anytime scorer",
        "player to score",
    ]

    if any(palabra in texto for palabra in palabras_marcador):
        return "Posible cobertura: marcador exacto"

    if any(palabra in texto for palabra in palabras_especiales):
        return "Mercado especial de jugador"

    return "Direccional"


def calcular_consenso(
    posiciones: pd.DataFrame,
) -> pd.DataFrame:
    """Agrupa mercados y lados repetidos entre distintos traders."""

    if posiciones.empty:
        return pd.DataFrame()

    tabla = posiciones.copy()

    tabla["Peso_Ranking"] = tabla["Ranking"].map(calcular_peso_ranking)

    tabla["Peso_Capital"] = (
        tabla["Valor_Actual_USD"]
        .clip(lower=0)
        .pow(0.5)
    )

    tabla["Peso_Total"] = (
        tabla["Peso_Ranking"] * tabla["Peso_Capital"]
    )

    agrupado = (
        tabla.groupby(
            ["Mercado", "Lado"],
            dropna=False,
        )
        .agg(
            Traders_Coincidentes=("Wallet", "nunique"),
            Capital_Visible_USD=("Valor_Actual_USD", "sum"),
            Precio_Entrada_Promedio=("Precio_Entrada", "mean"),
            Precio_Actual_Promedio=("Precio_Actual", "mean"),
            Ranking_Mejor=("Ranking", "min"),
            Peso_Consenso=("Peso_Total", "sum"),
            Traders=("Usuario", lambda valores: ", ".join(
                sorted(set(str(valor) for valor in valores))
            )),
        )
        .reset_index()
    )

    maximo_peso = agrupado["Peso_Consenso"].max()

    if maximo_peso > 0:
        agrupado["WCI"] = (
            agrupado["Peso_Consenso"] / maximo_peso * 100
        ).round(1)
    else:
        agrupado["WCI"] = 0.0

    agrupado["Tipo"] = agrupado["Mercado"].map(
        detectar_tipo_mercado
    )

    agrupado = agrupado.sort_values(
        by=[
            "Traders_Coincidentes",
            "Capital_Visible_USD",
            "WCI",
        ],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    return agrupado


def mostrar_resumen(
    posiciones: pd.DataFrame,
    consenso: pd.DataFrame,
) -> None:
    """Muestra resultados principales en la terminal."""

    print("\n" + "=" * 110)
    print("WHALESPORTS AI — POSICIONES ACTIVAS")
    print("=" * 110)
    print(f"Posiciones relevantes encontradas: {len(posiciones)}")

    if posiciones.empty:
        print("No se encontraron posiciones por encima del filtro.")
        return

    traders_con_posiciones = posiciones["Wallet"].nunique()

    print(
        "Traders con posiciones relevantes: "
        f"{traders_con_posiciones}"
    )

    print("\n" + "=" * 110)
    print("PRINCIPALES COINCIDENCIAS")
    print("=" * 110)

    principales = consenso[
        consenso["Traders_Coincidentes"] >= 2
    ].head(25).copy()

    if principales.empty:
        print("Todavía no hay posiciones repetidas entre traders.")
        return

    columnas = [
        "Mercado",
        "Lado",
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "WCI",
        "Tipo",
    ]

    pd.set_option("display.max_colwidth", 55)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)

    print(principales[columnas].to_string(index=False))


def main() -> None:
    print("Cargando Top 50 Sports Traders...")

    traders = cargar_traders()

    print(f"Traders cargados: {len(traders)}")
    print("Consultando posiciones públicas activas...\n")

    posiciones = descargar_todas_las_posiciones(traders)

    posiciones.to_csv(
        OUTPUT_POSITIONS_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    consenso = calcular_consenso(posiciones)

    consenso.to_csv(
        OUTPUT_CONSENSUS_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    mostrar_resumen(posiciones, consenso)

    print("\nArchivos creados:")
    print(f"- {OUTPUT_POSITIONS_FILE}")
    print(f"- {OUTPUT_CONSENSUS_FILE}")


if __name__ == "__main__":
    main()