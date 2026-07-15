from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


HISTORY_FILE = Path("market_history.csv")
OUTPUT_FILE = Path("early_entry_signals.csv")

MIN_CURRENT_TRADERS = 3
MIN_CURRENT_WCI = 60
MIN_CURRENT_CAPITAL = 10_000

WINDOWS_MINUTES = [15, 30, 60]


def cargar_historial() -> pd.DataFrame:
    if not HISTORY_FILE.exists():
        raise FileNotFoundError(
            "No se encontró market_history.csv.\n"
            "Primero ejecuta: python snapshot_history.py"
        )

    tabla = pd.read_csv(HISTORY_FILE)

    columnas_necesarias = {
        "Timestamp_UTC",
        "Signal_ID",
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
    }

    faltantes = columnas_necesarias - set(tabla.columns)

    if faltantes:
        raise ValueError(
            "Faltan columnas en market_history.csv: "
            + ", ".join(sorted(faltantes))
        )

    tabla["Timestamp_UTC"] = pd.to_datetime(
        tabla["Timestamp_UTC"],
        errors="coerce",
        utc=True,
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
        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0)

    tabla = tabla.dropna(
        subset=["Timestamp_UTC", "Signal_ID"]
    ).copy()

    return tabla


def snapshot_actual(historial: pd.DataFrame) -> pd.DataFrame:
    ultimo_timestamp = historial["Timestamp_UTC"].max()

    actual = historial[
        historial["Timestamp_UTC"] == ultimo_timestamp
    ].copy()

    return actual


def obtener_snapshot_pasado(
    historial: pd.DataFrame,
    timestamp_actual: pd.Timestamp,
    minutos: int,
) -> pd.DataFrame:
    objetivo = timestamp_actual - timedelta(minutes=minutos)

    anteriores = historial[
        historial["Timestamp_UTC"] <= objetivo
    ]

    if anteriores.empty:
        return pd.DataFrame()

    timestamp_elegido = anteriores["Timestamp_UTC"].max()

    return anteriores[
        anteriores["Timestamp_UTC"] == timestamp_elegido
    ].copy()


def valor_pasado(
    fila_actual: pd.Series,
    pasado: pd.DataFrame,
    columna: str,
) -> float:
    if pasado.empty:
        return 0.0

    coincidencia = pasado[
        pasado["Signal_ID"] == fila_actual["Signal_ID"]
    ]

    if coincidencia.empty:
        return 0.0

    return float(coincidencia.iloc[0][columna])


def texto_pasado(
    fila_actual: pd.Series,
    pasado: pd.DataFrame,
    columna: str,
) -> str:
    if pasado.empty:
        return ""

    coincidencia = pasado[
        pasado["Signal_ID"] == fila_actual["Signal_ID"]
    ]

    if coincidencia.empty:
        return ""

    return str(coincidencia.iloc[0][columna])


def contar_traders_nuevos(
    traders_actuales: str,
    traders_pasados: str,
) -> int:
    actuales = {
        trader.strip()
        for trader in str(traders_actuales).split(",")
        if trader.strip()
    }

    pasados = {
        trader.strip()
        for trader in str(traders_pasados).split(",")
        if trader.strip()
    }

    return len(actuales - pasados)


def evaluar_precio(
    precio_entrada: float,
    precio_actual: float,
) -> tuple[float, str]:
    if precio_entrada <= 0 or precio_actual <= 0:
        return 0.0, "Precio insuficiente"

    cambio = (
        (precio_actual - precio_entrada)
        / precio_entrada
        * 100
    )

    if cambio <= 3:
        estado = "Entrada todavía cercana"
    elif cambio <= 8:
        estado = "Movimiento moderado"
    elif cambio <= 15:
        estado = "Precio ya extendido"
    else:
        estado = "Probablemente tarde para copiar"

    return round(cambio, 2), estado


def calcular_early_entry_score(fila: pd.Series) -> float:
    puntos = 0.0

    nuevos_15 = float(fila.get("Traders_Nuevos_15m", 0))
    nuevos_30 = float(fila.get("Traders_Nuevos_30m", 0))
    capital_30 = float(fila.get("Capital_Nuevo_30m", 0))
    wci_cambio_30 = float(fila.get("Cambio_WCI_30m", 0))
    cambio_precio = float(fila.get("Cambio_Precio_30m_Pct", 0))
    traders_actuales = float(
        fila.get("Traders_Coincidentes", 0)
    )
    wci_actual = float(fila.get("WCI", 0))

    puntos += min(nuevos_15 / 3, 1) * 25
    puntos += min(nuevos_30 / 5, 1) * 15
    puntos += min(capital_30 / 250_000, 1) * 20
    puntos += min(max(wci_cambio_30, 0) / 15, 1) * 15
    puntos += min(traders_actuales / 8, 1) * 10
    puntos += min(wci_actual / 100, 1) * 15

    if cambio_precio > 15:
        puntos -= 30
    elif cambio_precio > 8:
        puntos -= 18
    elif cambio_precio > 3:
        puntos -= 8

    return round(max(0, min(puntos, 100)), 1)


def clasificar_score(score: float) -> str:
    if score >= 80:
        return "Entrada temprana muy fuerte"

    if score >= 65:
        return "Entrada temprana fuerte"

    if score >= 50:
        return "Entrada temprana moderada"

    return "Seguimiento"


def crear_señales(historial: pd.DataFrame) -> pd.DataFrame:
    actual = snapshot_actual(historial)

    if actual.empty:
        return pd.DataFrame()

    timestamp_actual = actual["Timestamp_UTC"].max()

    snapshots_pasados = {
        minutos: obtener_snapshot_pasado(
            historial,
            timestamp_actual,
            minutos,
        )
        for minutos in WINDOWS_MINUTES
    }

    if snapshots_pasados[30].empty:
        print(
            "Todavía no existe un snapshot válido "
            "de hace aproximadamente 30 minutos."
        )
        return pd.DataFrame()
    registros = []

    for _, fila in actual.iterrows():
        if fila["Tipo"] != "Direccional":
            continue

        if (
            fila["Traders_Coincidentes"]
            < MIN_CURRENT_TRADERS
        ):
            continue

        if fila["WCI"] < MIN_CURRENT_WCI:
            continue

        if (
            fila["Capital_Visible_USD"]
            < MIN_CURRENT_CAPITAL
        ):
            continue

        registro = fila.to_dict()

        for minutos, pasado in snapshots_pasados.items():
            traders_pasados = valor_pasado(
                fila,
                pasado,
                "Traders_Coincidentes",
            )

            capital_pasado = valor_pasado(
                fila,
                pasado,
                "Capital_Visible_USD",
            )

            wci_pasado = valor_pasado(
                fila,
                pasado,
                "WCI",
            )

            precio_pasado = valor_pasado(
                fila,
                pasado,
                "Precio_Actual_Promedio",
            )

            lista_traders_pasados = texto_pasado(
                fila,
                pasado,
                "Traders",
            )

            registro[
                f"Cambio_Traders_{minutos}m"
            ] = int(
                fila["Traders_Coincidentes"]
                - traders_pasados
            )

            registro[
                f"Traders_Nuevos_{minutos}m"
            ] = contar_traders_nuevos(
                fila["Traders"],
                lista_traders_pasados,
            )

            registro[
                f"Capital_Nuevo_{minutos}m"
            ] = round(
                fila["Capital_Visible_USD"]
                - capital_pasado,
                2,
            )

            registro[
                f"Cambio_WCI_{minutos}m"
            ] = round(
                fila["WCI"] - wci_pasado,
                2,
            )

            registro[
                f"Cambio_Precio_{minutos}m"
            ] = round(
                fila["Precio_Actual_Promedio"]
                - precio_pasado,
                4,
            )

        cambio_entrada, estado_precio = evaluar_precio(
            float(fila["Precio_Entrada_Promedio"]),
            float(fila["Precio_Actual_Promedio"]),
        )

        registro[
            "Cambio_Desde_Entrada_Pct"
        ] = cambio_entrada

        registro["Estado_Precio"] = estado_precio

        registros.append(registro)

    resultado = pd.DataFrame(registros)

    if resultado.empty:
        return resultado

    resultado["Early_Entry_Score"] = resultado.apply(
        calcular_early_entry_score,
        axis=1,
    )

    resultado["Nivel_Early_Entry"] = (
        resultado["Early_Entry_Score"].map(
            clasificar_score
        )
    )

    resultado = resultado.sort_values(
        by=[
            "Early_Entry_Score",
            "Traders_Nuevos_30m",
            "Capital_Nuevo_30m",
            "WCI",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    return resultado


def mostrar_resumen(resultado: pd.DataFrame) -> None:
    print("\n" + "=" * 120)
    print("WHALESPORTS AI — EARLY ENTRY DETECTOR")
    print("=" * 120)

    if resultado.empty:
        print(
            "Todavía no hay suficiente historial "
            "para detectar entradas tempranas."
        )
        return

    columnas = [
        "Mercado",
        "Lado",
        "Traders_Coincidentes",
        "Traders_Nuevos_15m",
        "Traders_Nuevos_30m",
        "Capital_Nuevo_30m",
        "Cambio_WCI_30m",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "Cambio_Desde_Entrada_Pct",
        "Estado_Precio",
        "Early_Entry_Score",
        "Nivel_Early_Entry",
    ]

    columnas = [
        columna
        for columna in columnas
        if columna in resultado.columns
    ]

    pd.set_option("display.width", 260)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_colwidth", 55)

    print(
        resultado[columnas]
        .head(20)
        .to_string(index=False)
    )


def main() -> None:
    historial = cargar_historial()
    resultado = crear_señales(historial)

    resultado.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    mostrar_resumen(resultado)

    print(f"\nArchivo creado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()