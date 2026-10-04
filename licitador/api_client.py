"""Cliente de la API pública de Mercado Público (v1).

Documentación: https://api.mercadopublico.cl/modules/api.aspx
"""
from __future__ import annotations

import time
from datetime import date

import httpx

from . import config

ESTADOS = {
    5: "Publicada",
    6: "Cerrada",
    7: "Desierta",
    8: "Adjudicada",
    18: "Revocada",
    19: "Suspendida",
}

# Códigos de error que devuelve la API en el cuerpo JSON.
ERROR_SIMULTANEAS = 10500


class MercadoPublicoError(RuntimeError):
    pass


class MercadoPublicoClient:
    def __init__(self, ticket: str | None = None, base: str | None = None,
                 delay: float | None = None, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.ticket = ticket if ticket is not None else config.TICKET
        if not self.ticket:
            raise MercadoPublicoError(
                "Falta el ticket de la API. Defínelo en la variable de entorno MP_TICKET "
                "(se solicita en https://api.mercadopublico.cl)."
            )
        self.base = (base or config.API_BASE).rstrip("/")
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._last = 0.0
        self.requests = 0

    def close(self):
        self._http.close()

    def _get(self, path: str, params: dict, retries: int = 5) -> dict:
        params = {**params, "ticket": self.ticket}
        backoff = 2.0
        for intento in range(retries):
            espera = self.delay - (time.monotonic() - self._last)
            if espera > 0:
                time.sleep(espera)
            self._last = time.monotonic()
            self.requests += 1
            try:
                r = self._http.get(f"{self.base}/{path}", params=params)
            except httpx.HTTPError as e:
                if intento == retries - 1:
                    raise MercadoPublicoError(f"Error de red: {e}") from e
                time.sleep(backoff)
                backoff *= 2
                continue
            try:
                data = r.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and "Codigo" in data and "Listado" not in data:
                # Error informado por la API (ticket inválido, peticiones simultáneas, etc.)
                if data.get("Codigo") == ERROR_SIMULTANEAS and intento < retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise MercadoPublicoError(f"API {data.get('Codigo')}: {data.get('Mensaje')}")
            if r.status_code >= 500 and intento < retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            if r.status_code != 200 or data is None:
                raise MercadoPublicoError(f"HTTP {r.status_code}: {r.text[:200]}")
            return data
        raise MercadoPublicoError("Se agotaron los reintentos")

    # --- Licitaciones -------------------------------------------------------

    def listar(self, estado: str | None = None, fecha: date | None = None,
               organismo: str | None = None, proveedor: str | None = None) -> list[dict]:
        """Listado resumido (CodigoExterno, Nombre, CodigoEstado, FechaCierre).

        estado: activas | publicada | cerrada | desierta | adjudicada | revocada | suspendida | todos
        """
        params: dict = {}
        if estado:
            params["estado"] = estado
        if fecha:
            params["fecha"] = fecha.strftime("%d%m%Y")
        if organismo:
            params["CodigoOrganismo"] = organismo
        if proveedor:
            params["CodigoProveedor"] = proveedor
        return self._get("licitaciones.json", params).get("Listado") or []

    def detalle(self, codigo: str) -> dict | None:
        listado = self._get("licitaciones.json", {"codigo": codigo}).get("Listado") or []
        return listado[0] if listado else None

    # --- Empresas -----------------------------------------------------------

    def buscar_proveedor(self, rut: str) -> list[dict]:
        """rut con puntos y guion, p. ej. 70.017.820-k"""
        data = self._get("Empresas/BuscarProveedor", {"rutempresaproveedor": rut})
        return data.get("listaEmpresas") or []
