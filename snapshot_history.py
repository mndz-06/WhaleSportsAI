from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


CONSENSUS_FILE = Path("sports_consensus_v2.csv")
HISTORY_FILE = Path("market_history.csv")

# Conservaremos 30 días de historial.
HISTORY_DAYS = 30


def cargar_consenso() -> pd.DataFrame:
    if not CONSENSUS_FILE.exists():
        raise FileNotFoundError(
            "No se encontró sports_consensus_v2.csv.\n"
            "Primero ejecuta: python consensus_v2.py"
        )

    tabla = pd.read_csv(CONSENSUS_FILE)

    columnas_necesarias = [
        "Condition_ID",
        "Mercado",
        "Lado",
        "Tipo",
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "Consenso_Porcentaje",
        "WCI",
        "Traders",
    ]

    faltantes = [
        columna
        for columna in columnas_necesarias
        if columna not in tabla.columns
    ]

    if faltantes:
        raise ValueError(
            "Faltan columnas en sports_consensus_v2.csv: "
            + ", ".join(faltantes)
        )

    return tabla[columnas_necesarias].copy()


def cargar_historial() -> pd.DataFrame:
    if not HISTORY_FILE.exists():
        return pd.DataFrame()

    try:
        historial = pd.read_csv(HISTORY_FILE)
    except Exception:
        return pd.DataFrame()

    if "Timestamp_UTC" in historial.columns:
        historial["Timestamp_UTC"] = pd.to_datetime(
            historial["Timestamp_UTC"],
            errors="coerce",
            utc=True,
        )

    return historial


def preparar_snapshot(consenso: pd.DataFrame) -> pd.DataFrame:
    ahora = datetime.now(timezone.utc)

    snapshot = consenso.copy()
    snapshot.insert(
        0,
        "Timestamp_UTC",
        ahora.isoformat(),
    )

    snapshot["Signal_ID"] = (
        snapshot["Condition_ID"].fillna("").astype(str)
        + "|"
        + snapshot["Lado"].fillna("").astype(str)
    )

    columnas_numericas = [
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "Consenso_Porcentaje",
        "WCI",
    ]

    for columna in columnas_numericas:
        snapshot[columna] = pd.to_numeric(
            snapshot[columna],
            errors="coerce",
        ).fillna(0)

    return snapshot


def limpiar_historial(historial: pd.DataFrame) -> pd.DataFrame:
    if historial.empty:
        return historial

    historial["Timestamp_UTC"] = pd.to_datetime(
        historial["Timestamp_UTC"],
        errors="coerce",
        utc=True,
    )

    limite = datetime.now(timezone.utc) - timedelta(
        days=HISTORY_DAYS
    )

    historial = historial[
        historial["Timestamp_UTC"] >= limite
    ].copy()

    historial = historial.drop_duplicates(
        subset=["Timestamp_UTC", "Signal_ID"],
        keep="last",
    )

    historial = historial.sort_values(
        by=["Timestamp_UTC", "Signal_ID"]
    ).reset_index(drop=True)

    historial["Timestamp_UTC"] = (
        historial["Timestamp_UTC"]
        .dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    )

    return historial


def main() -> None:
    consenso = cargar_consenso()
    snapshot = preparar_snapshot(consenso)
    historial_anterior = cargar_historial()

    if historial_anterior.empty:
        historial_actualizado = snapshot
    else:
        historial_actualizado = pd.concat(
            [historial_anterior, snapshot],
            ignore_index=True,
        )

    historial_actualizado = limpiar_historial(
        historial_actualizado
    )

    historial_actualizado.to_csv(
        HISTORY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("Snapshot guardado correctamente.")
    print(f"Mercados registrados ahora: {len(snapshot)}")
    print(
        "Registros totales en historial: "
        f"{len(historial_actualizado)}"
    )
    print(f"Archivo: {HISTORY_FILE}")


if __name__ == "__main__":
    main()