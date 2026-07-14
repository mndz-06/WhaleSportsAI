from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from telegram_alerts import enviar_mensaje


load_dotenv()

CONSENSUS_FILE = Path("sports_consensus_v2.csv")
STATE_FILE = Path("alert_state.json")

MIN_ALERT_TRADERS = int(os.getenv("MIN_ALERT_TRADERS", "3"))
MIN_ALERT_WCI = float(os.getenv("MIN_ALERT_WCI", "65"))

MIN_CAPITAL_USD = 10_000
IMPORTANT_WCI_CHANGE = 8
IMPORTANT_TRADER_CHANGE = 2


def cargar_estado() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def guardar_estado(estado: dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(
            estado,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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


def identificador_señal(fila: pd.Series) -> str:
    condition_id = str(fila.get("Condition_ID", "")).strip()
    lado = str(fila.get("Lado", "")).strip()

    if condition_id:
        return f"{condition_id}|{lado}"

    return f"{fila.get('Mercado', '')}|{lado}"


def preparar_señales() -> pd.DataFrame:
    if not CONSENSUS_FILE.exists():
        raise FileNotFoundError(
            "No se encontró sports_consensus_v2.csv"
        )

    tabla = pd.read_csv(CONSENSUS_FILE)

    columnas_numericas = [
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "Consenso_Porcentaje",
        "WCI",
    ]

    for columna in columnas_numericas:
        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0)

    señales = tabla[
        (tabla["Traders_Coincidentes"] >= MIN_ALERT_TRADERS)
        & (tabla["WCI"] >= MIN_ALERT_WCI)
        & (tabla["Capital_Visible_USD"] >= MIN_CAPITAL_USD)
        & (tabla["Tipo"] == "Direccional")
    ].copy()

    señales["Signal_ID"] = señales.apply(
        identificador_señal,
        axis=1,
    )

    return señales


def cambio_importante(
    fila: pd.Series,
    anterior: dict[str, Any] | None,
) -> tuple[bool, str]:
    if anterior is None:
        return True, "Nueva coincidencia"

    traders_actuales = int(fila["Traders_Coincidentes"])
    traders_anteriores = int(anterior.get("traders", 0))

    wci_actual = float(fila["WCI"])
    wci_anterior = float(anterior.get("wci", 0))

    capital_actual = float(fila["Capital_Visible_USD"])
    capital_anterior = float(anterior.get("capital", 0))

    if traders_actuales - traders_anteriores >= IMPORTANT_TRADER_CHANGE:
        return True, "Se sumaron varias ballenas"

    if wci_actual - wci_anterior >= IMPORTANT_WCI_CHANGE:
        return True, "Subió fuertemente el WCI"

    if capital_anterior > 0 and capital_actual >= capital_anterior * 1.5:
        return True, "Aumentó fuertemente el capital visible"

    return False, ""


def crear_mensaje(
    fila: pd.Series,
    motivo: str,
) -> str:
    advertencia = str(fila.get("Advertencia", "")).strip()

    mensaje = (
        "🐋 <b>WhaleSports AI — alerta deportiva</b>\n\n"
        f"<b>Motivo:</b> {motivo}\n"
        f"<b>Mercado:</b> {fila['Mercado']}\n"
        f"<b>Pick:</b> {fila['Lado']}\n"
        f"<b>Ballenas coincidentes:</b> "
        f"{int(fila['Traders_Coincidentes'])}\n"
        f"<b>Capital visible:</b> "
        f"{dinero_corto(fila['Capital_Visible_USD'])}\n"
        f"<b>Entrada promedio:</b> "
        f"{precio_centavos(fila['Precio_Entrada_Promedio'])}\n"
        f"<b>Precio aproximado:</b> "
        f"{precio_centavos(fila['Precio_Actual_Promedio'])}\n"
        f"<b>Consenso neto:</b> "
        f"{fila['Consenso_Porcentaje']:.1f}%\n"
        f"<b>WCI:</b> {fila['WCI']:.1f}/100\n"
        f"<b>Traders:</b> {fila.get('Traders', '')}"
    )

    if advertencia:
        mensaje += f"\n\n⚠️ {advertencia}"

    mensaje += (
        "\n\n<i>Herramienta de análisis; "
        "revisa las reglas del mercado antes de copiar el pick.</i>"
    )

    return mensaje


def main() -> None:
    señales = preparar_señales()
    estado_anterior = cargar_estado()
    estado_nuevo: dict[str, Any] = {}
    primera_ejecucion = not STATE_FILE.exists()

    alertas_enviadas = 0

    for _, fila in señales.iterrows():
        signal_id = fila["Signal_ID"]
        anterior = estado_anterior.get(signal_id)

        alertar, motivo = cambio_importante(
            fila,
            anterior,
        )

        estado_nuevo[signal_id] = {
            "mercado": str(fila["Mercado"]),
            "lado": str(fila["Lado"]),
            "traders": int(fila["Traders_Coincidentes"]),
            "capital": float(fila["Capital_Visible_USD"]),
            "wci": float(fila["WCI"]),
            "precio": float(fila["Precio_Actual_Promedio"]),
        }

        if primera_ejecucion or not alertar:
            continue

        enviar_mensaje(
            crear_mensaje(
                fila,
                motivo,
            )
        )
        alertas_enviadas += 1

    guardar_estado(estado_nuevo)

    print(f"Señales candidatas: {len(señales)}")
    print(f"Alertas enviadas: {alertas_enviadas}")


if __name__ == "__main__":
    main()