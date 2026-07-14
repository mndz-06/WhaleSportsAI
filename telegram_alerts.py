from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def enviar_mensaje(mensaje: str) -> None:
    """Envía un mensaje al chat configurado en Telegram."""

    if not BOT_TOKEN:
        raise ValueError(
            "Falta TELEGRAM_BOT_TOKEN en el archivo .env"
        )

    if not CHAT_ID:
        raise ValueError(
            "Falta TELEGRAM_CHAT_ID en el archivo .env"
        )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    respuesta = requests.post(
        url,
        data=payload,
        timeout=30,
    )

    respuesta.raise_for_status()

    datos = respuesta.json()

    if not datos.get("ok"):
        raise RuntimeError(
            f"Telegram rechazó el mensaje: {datos}"
        )


def main() -> None:
    mensaje_prueba = (
        "🐋 <b>WhaleSports AI conectado</b>\n\n"
        "La conexión con Telegram funciona correctamente.\n"
        "Todavía no es una señal de apuesta."
    )

    try:
        enviar_mensaje(mensaje_prueba)
    except Exception as error:
        print("No se pudo enviar el mensaje.")
        print(f"Detalle: {error}")
        sys.exit(1)

    print("Mensaje de prueba enviado correctamente.")


if __name__ == "__main__":
    main()