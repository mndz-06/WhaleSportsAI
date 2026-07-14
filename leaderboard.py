from __future__ import annotations

import sys
from typing import Any

import pandas as pd
import requests


LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"
TOP_TRADERS = 50


def obtener_top_traders(limite: int = TOP_TRADERS) -> list[dict[str, Any]]:
    """Descarga los traders del Sports Leaderboard de Polymarket."""

    parametros = {
        "category": "SPORTS",
        "timePeriod": "ALL",
        "orderBy": "PNL",
        "limit": limite,
    }

    try:
        respuesta = requests.get(
            LEADERBOARD_URL,
            params=parametros,
            timeout=30,
        )
        respuesta.raise_for_status()
    except requests.RequestException as error:
        print("\nNo se pudo conectar con Polymarket.")
        print(f"Detalle del error: {error}")
        sys.exit(1)

    datos = respuesta.json()

    if not isinstance(datos, list):
        print("Polymarket devolvió una respuesta inesperada.")
        sys.exit(1)

    return datos


def limpiar_datos(traders: list[dict[str, Any]]) -> pd.DataFrame:
    """Convierte la información recibida en una tabla más fácil de leer."""

    registros = []

    for trader in traders:
        registros.append(
            {
                "Ranking": trader.get("rank"),
                "Usuario": trader.get("userName") or "Sin nombre",
                "Wallet": trader.get("proxyWallet"),
                "Volumen": float(trader.get("vol") or 0),
                "Ganancia_PNL": float(trader.get("pnl") or 0),
                "Verificado": trader.get("verifiedBadge", False),
            }
        )

    tabla = pd.DataFrame(registros)

    if not tabla.empty:
        tabla = tabla.sort_values("Ranking").reset_index(drop=True)

    return tabla


def mostrar_tabla(tabla: pd.DataFrame) -> None:
    """Muestra la tabla en la terminal y la guarda como archivo CSV."""

    pd.set_option("display.max_rows", 60)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 180)
    pd.set_option("display.max_colwidth", 20)

    tabla_visible = tabla.copy()

    tabla_visible["Volumen"] = tabla_visible["Volumen"].map(
        lambda valor: f"${valor:,.2f}"
    )
    tabla_visible["Ganancia_PNL"] = tabla_visible["Ganancia_PNL"].map(
        lambda valor: f"${valor:,.2f}"
    )
    tabla_visible["Wallet"] = tabla_visible["Wallet"].map(
        lambda wallet: (
            f"{wallet[:8]}...{wallet[-6:]}"
            if isinstance(wallet, str) and len(wallet) > 16
            else wallet
        )
    )

    print("\n" + "=" * 100)
    print("WHALESPORTS AI — TOP 50 SPORTS TRADERS DE POLYMARKET")
    print("=" * 100)
    print(tabla_visible.to_string(index=False))
    print("=" * 100)

    nombre_archivo = "top_50_sports_traders.csv"
    tabla.to_csv(nombre_archivo, index=False, encoding="utf-8-sig")

    print(f"\nArchivo guardado correctamente: {nombre_archivo}")
    print(f"Traders encontrados: {len(tabla)}")


def main() -> None:
    print("Consultando el Sports Leaderboard de Polymarket...")

    traders = obtener_top_traders()
    tabla = limpiar_datos(traders)
    mostrar_tabla(tabla)


if __name__ == "__main__":
    main()