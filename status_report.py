from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from telegram_alerts import enviar_mensaje


CONSENSUS_FILE = Path("sports_consensus_v2.csv")

MIN_TRADERS = 3
MIN_WCI = 65
MIN_CAPITAL_USD = 10_000


def dinero_corto(valor: float) -> str:
    numero = float(valor)

    if abs(numero) >= 1_000_000:
        return f"${numero / 1_000_000:.2f}M"

    if abs(numero) >= 1_000:
        return f"${numero / 1_000:.1f}K"

    return f"${numero:,.0f}"


def precio_centavos(valor: float) -> str:
    numero = float(valor)

    if numero <= 1:
        numero *= 100

    return f"{numero:.1f}¢"


def cargar_consenso() -> pd.DataFrame:
    if not CONSENSUS_FILE.exists():
        raise FileNotFoundError(
            "No se encontró sports_consensus_v2.csv"
        )

    tabla = pd.read_csv(CONSENSUS_FILE)

    columnas_numericas = [
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Actual_Promedio",
        "Consenso_Porcentaje",
        "WCI",
    ]

    for columna in columnas_numericas:
        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0)

    return tabla


def crear_reporte(tabla: pd.DataFrame) -> str:
    candidatas = tabla[
        (tabla["Traders_Coincidentes"] >= MIN_TRADERS)
        & (tabla["WCI"] >= MIN_WCI)
        & (tabla["Capital_Visible_USD"] >= MIN_CAPITAL_USD)
        & (tabla["Tipo"] == "Direccional")
    ].copy()

    candidatas = candidatas.sort_values(
        by=[
            "WCI",
            "Traders_Coincidentes",
            "Capital_Visible_USD",
        ],
        ascending=[False, False, False],
    )

    ahora = datetime.now(timezone.utc).strftime(
        "%d/%m/%Y %H:%M UTC"
    )

    mensaje = (
        "🐋 <b>WhaleSports AI — reporte de estado</b>\n\n"
        f"<b>Último escaneo:</b> {ahora}\n"
        f"<b>Señales candidatas:</b> {len(candidatas)}\n"
        "<b>Estado:</b> sistema funcionando correctamente"
    )

    if candidatas.empty:
        return mensaje + (
            "\n\nNo hay señales que superen "
            "actualmente los filtros."
        )

    mejor = candidatas.iloc[0]

    mensaje += (
        "\n\n🔥 <b>Señal más fuerte actual</b>\n"
        f"<b>Mercado:</b> {mejor['Mercado']}\n"
        f"<b>Pick:</b> {mejor['Lado']}\n"
        f"<b>Ballenas:</b> "
        f"{int(mejor['Traders_Coincidentes'])}\n"
        f"<b>Capital visible:</b> "
        f"{dinero_corto(mejor['Capital_Visible_USD'])}\n"
        f"<b>Precio aproximado:</b> "
        f"{precio_centavos(mejor['Precio_Actual_Promedio'])}\n"
        f"<b>Consenso neto:</b> "
        f"{mejor['Consenso_Porcentaje']:.1f}%\n"
        f"<b>WCI:</b> {mejor['WCI']:.1f}/100"
    )

    mensaje += (
        "\n\n<i>Este reporte confirma que el sistema sigue activo. "
        "No es una recomendación garantizada.</i>"
    )

    return mensaje


def main() -> None:
    tabla = cargar_consenso()
    mensaje = crear_reporte(tabla)
    enviar_mensaje(mensaje)

    print("Reporte de estado enviado correctamente.")


if __name__ == "__main__":
    main()