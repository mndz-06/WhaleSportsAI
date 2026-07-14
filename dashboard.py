from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


CONSENSUS_FILE = Path("sports_consensus_v2.csv")
POSITIONS_FILE = Path("top_50_active_positions.csv")


st.set_page_config(
    page_title="WhaleSports AI",
    page_icon="🐋",
    layout="wide",
)


def cargar_csv(ruta: Path) -> pd.DataFrame:
    """Carga un archivo CSV y devuelve una tabla vacía si no existe."""

    if not ruta.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(ruta)
    except Exception as error:
        st.error(f"No se pudo abrir {ruta.name}: {error}")
        return pd.DataFrame()


def formato_dinero(valor: float) -> str:
    """Convierte una cifra a formato de dinero."""

    try:
        return f"${float(valor):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def formato_precio(valor: float) -> str:
    """Convierte un precio decimal a centavos."""

    try:
        numero = float(valor)

        if numero <= 1:
            return f"{numero * 100:.1f}¢"

        return f"{numero:.1f}¢"
    except (TypeError, ValueError):
        return "N/D"


def nivel_confianza(wci: float) -> str:
    """Clasifica el WCI en niveles sencillos."""

    try:
        puntuacion = float(wci)
    except (TypeError, ValueError):
        puntuacion = 0

    if puntuacion >= 90:
        return "Excepcional"

    if puntuacion >= 80:
        return "Muy alta"

    if puntuacion >= 70:
        return "Alta"

    if puntuacion >= 60:
        return "Moderada"

    return "Baja"


def preparar_consenso(tabla: pd.DataFrame) -> pd.DataFrame:
    """Limpia las columnas principales del consenso."""

    if tabla.empty:
        return tabla

    columnas_numericas = [
        "Traders_Coincidentes",
        "Capital_Visible_USD",
        "Precio_Entrada_Promedio",
        "Precio_Actual_Promedio",
        "Ranking_Mejor",
        "Peso_Consenso",
        "WCI",
    ]

    for columna in columnas_numericas:
        if columna in tabla.columns:
            tabla[columna] = pd.to_numeric(
                tabla[columna],
                errors="coerce",
            ).fillna(0)

    if "Tipo" not in tabla.columns:
        tabla["Tipo"] = "Sin clasificar"

    if "Traders" not in tabla.columns:
        tabla["Traders"] = ""

    tabla["Confianza"] = tabla["WCI"].map(nivel_confianza)

    return tabla


def mostrar_metricas(
    consenso: pd.DataFrame,
    posiciones: pd.DataFrame,
) -> None:
    """Muestra las métricas principales del sistema."""

    total_traders = 0
    total_posiciones = len(posiciones)
    total_mercados = 0
    capital_visible = 0.0

    if not posiciones.empty and "Wallet" in posiciones.columns:
        total_traders = posiciones["Wallet"].nunique()

    if not consenso.empty:
        total_mercados = len(consenso)

        if "Capital_Visible_USD" in consenso.columns:
            capital_visible = consenso["Capital_Visible_USD"].sum()

    columna_1, columna_2, columna_3, columna_4 = st.columns(4)

    columna_1.metric(
        "Traders analizados",
        total_traders,
    )

    columna_2.metric(
        "Posiciones activas",
        total_posiciones,
    )

    columna_3.metric(
        "Mercados agrupados",
        total_mercados,
    )

    columna_4.metric(
        "Capital visible",
        formato_dinero(capital_visible),
    )


def mostrar_alertas(consenso: pd.DataFrame) -> None:
    """Muestra las mejores coincidencias como tarjetas."""

    st.subheader("🔥 Principales señales")

    señales = consenso[
        (consenso["Traders_Coincidentes"] >= 3)
        & (consenso["WCI"] >= 60)
        & (consenso["Tipo"] == "Direccional")
    ].head(10)

    if señales.empty:
        st.info(
            "No hay señales direccionales con al menos "
            "3 traders y WCI de 60 o más."
        )
        return

    for _, fila in señales.iterrows():
        with st.container(border=True):
            izquierda, centro, derecha = st.columns(
                [2.5, 1.2, 1.2]
            )

            with izquierda:
                st.markdown(f"### {fila['Mercado']}")
                st.markdown(f"**Pick:** {fila['Lado']}")

                traders = fila.get("Traders", "")

                if traders:
                    st.caption(f"Traders: {traders}")

            with centro:
                st.metric(
                    "Ballenas",
                    int(fila["Traders_Coincidentes"]),
                )
                st.metric(
                    "Capital visible",
                    formato_dinero(
                        fila["Capital_Visible_USD"]
                    ),
                )

            with derecha:
                st.metric(
                    "WCI",
                    f"{fila['WCI']:.1f}/100",
                )
                st.write(
                    f"**Confianza:** "
                    f"{fila['Confianza']}"
                )

                st.write(
                    "**Precio actual:** "
                    f"{formato_precio(fila['Precio_Actual_Promedio'])}"
                )


def mostrar_tabla_filtrada(consenso: pd.DataFrame) -> None:
    """Muestra filtros y tabla detallada."""

    st.subheader("📊 Consenso completo")

    columna_1, columna_2, columna_3 = st.columns(3)

    with columna_1:
        minimo_traders = st.slider(
            "Mínimo de traders coincidentes",
            min_value=1,
            max_value=20,
            value=2,
            step=1,
        )

    with columna_2:
        minimo_wci = st.slider(
            "WCI mínimo",
            min_value=0,
            max_value=100,
            value=40,
            step=5,
        )

    tipos_disponibles = sorted(
        consenso["Tipo"].dropna().unique().tolist()
    )

    with columna_3:
        tipos_elegidos = st.multiselect(
            "Tipo de mercado",
            options=tipos_disponibles,
            default=tipos_disponibles,
        )

    busqueda = st.text_input(
        "Buscar mercado o pick",
        placeholder="Ejemplo: Argentina, Francia, Over 2.5...",
    )

    filtrado = consenso[
        (consenso["Traders_Coincidentes"] >= minimo_traders)
        & (consenso["WCI"] >= minimo_wci)
        & (consenso["Tipo"].isin(tipos_elegidos))
    ].copy()

    if busqueda.strip():
        texto = busqueda.strip().lower()

        filtrado = filtrado[
            filtrado["Mercado"]
            .astype(str)
            .str.lower()
            .str.contains(texto, na=False)
            |
            filtrado["Lado"]
            .astype(str)
            .str.lower()
            .str.contains(texto, na=False)
        ]

    filtrado = filtrado.sort_values(
        by=[
            "Traders_Coincidentes",
            "WCI",
            "Capital_Visible_USD",
        ],
        ascending=[False, False, False],
    )

    tabla_visible = filtrado[
        [
            "Mercado",
            "Lado",
            "Traders_Coincidentes",
            "Capital_Visible_USD",
            "Precio_Entrada_Promedio",
            "Precio_Actual_Promedio",
            "WCI",
            "Confianza",
            "Tipo",
            "Traders",
        ]
    ].copy()

    tabla_visible = tabla_visible.rename(
        columns={
            "Mercado": "Mercado",
            "Lado": "Pick",
            "Traders_Coincidentes": "Ballenas",
            "Capital_Visible_USD": "Capital visible",
            "Precio_Entrada_Promedio": "Entrada promedio",
            "Precio_Actual_Promedio": "Precio actual",
            "WCI": "WCI",
            "Confianza": "Confianza",
            "Tipo": "Tipo",
            "Traders": "Traders",
        }
    )

    tabla_visible["Capital visible"] = (
        tabla_visible["Capital visible"].map(formato_dinero)
    )

    tabla_visible["Entrada promedio"] = (
        tabla_visible["Entrada promedio"].map(formato_precio)
    )

    tabla_visible["Precio actual"] = (
        tabla_visible["Precio actual"].map(formato_precio)
    )

    st.write(
        f"Resultados encontrados: **{len(tabla_visible)}**"
    )

    st.dataframe(
        tabla_visible,
        use_container_width=True,
        hide_index=True,
        height=600,
    )


def mostrar_posiciones_individuales(
    posiciones: pd.DataFrame,
) -> None:
    """Permite revisar las posiciones de cada trader."""

    st.subheader("🐋 Posiciones individuales")

    if posiciones.empty:
        st.warning("No hay posiciones individuales disponibles.")
        return

    usuarios = sorted(
        posiciones["Usuario"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    usuario_elegido = st.selectbox(
        "Selecciona un trader",
        options=["Todos"] + usuarios,
    )

    tabla = posiciones.copy()

    if usuario_elegido != "Todos":
        tabla = tabla[
            tabla["Usuario"] == usuario_elegido
        ]

    columnas_mostrar = [
        "Ranking",
        "Usuario",
        "Mercado",
        "Lado",
        "Valor_Actual_USD",
        "Precio_Entrada",
        "Precio_Actual",
        "PNL_USD",
        "PNL_Porcentaje",
    ]

    columnas_existentes = [
        columna
        for columna in columnas_mostrar
        if columna in tabla.columns
    ]

    tabla = tabla[columnas_existentes].copy()

    if "Valor_Actual_USD" in tabla.columns:
        tabla["Valor_Actual_USD"] = (
            tabla["Valor_Actual_USD"].map(formato_dinero)
        )

    if "PNL_USD" in tabla.columns:
        tabla["PNL_USD"] = tabla["PNL_USD"].map(
            formato_dinero
        )

    if "Precio_Entrada" in tabla.columns:
        tabla["Precio_Entrada"] = (
            tabla["Precio_Entrada"].map(formato_precio)
        )

    if "Precio_Actual" in tabla.columns:
        tabla["Precio_Actual"] = (
            tabla["Precio_Actual"].map(formato_precio)
        )

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        height=500,
    )


def main() -> None:
    st.title("🐋 WhaleSports AI")
    st.caption(
        "Seguimiento de posiciones públicas de los "
        "Top 50 traders del Sports Leaderboard de Polymarket."
    )

    st.warning(
        "Este panel es una herramienta de análisis. "
        "El WCI no representa una probabilidad garantizada "
        "ni asegura que un pick vaya a ganar."
    )

    if st.button("🔄 Actualizar datos del panel"):
        st.cache_data.clear()
        st.rerun()

    consenso = preparar_consenso(
        cargar_csv(CONSENSUS_FILE)
    )

    posiciones = cargar_csv(POSITIONS_FILE)

    if consenso.empty:
        st.error(
            "No se encontró información en sports_consensus.csv. "
            "Primero ejecuta: python positions.py"
        )
        return

    mostrar_metricas(consenso, posiciones)

    st.divider()

    mostrar_alertas(consenso)

    st.divider()

    mostrar_tabla_filtrada(consenso)

    st.divider()

    mostrar_posiciones_individuales(posiciones)


if __name__ == "__main__":
    main()