import os
from pathlib import Path

# Ticket de la API de Mercado Público. Se solicita gratis en
# https://api.mercadopublico.cl (registro con Clave Única).
TICKET = os.environ.get("MP_TICKET", "")
API_BASE = os.environ.get(
    "MP_API_BASE", "https://api.mercadopublico.cl/servicios/v1/publico"
)
DB_PATH = Path(os.environ.get("LICITADOR_DB", Path(__file__).resolve().parent.parent / "data" / "licitador.db"))
# Pausa entre llamadas: la API rechaza peticiones simultáneas y limita el uso diario.
REQUEST_DELAY = float(os.environ.get("MP_REQUEST_DELAY", "0.6"))
