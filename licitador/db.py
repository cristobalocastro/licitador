"""Almacenamiento local en SQLite de licitaciones e ítems."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config
from .api_client import ESTADOS

SCHEMA = """
CREATE TABLE IF NOT EXISTS licitaciones (
    codigo TEXT PRIMARY KEY,
    nombre TEXT,
    descripcion TEXT,
    estado_codigo INTEGER,
    tipo TEXT,
    moneda TEXT,
    monto_estimado REAL,
    organismo_codigo TEXT,
    organismo TEXT,
    unidad TEXT,
    region TEXT,
    comuna TEXT,
    fecha_publicacion TEXT,
    fecha_cierre TEXT,
    fecha_adjudicacion TEXT,
    num_oferentes INTEGER,
    url_acta TEXT,
    detalle_cargado INTEGER DEFAULT 0,
    raw TEXT,
    actualizado TEXT
);
CREATE TABLE IF NOT EXISTS items (
    codigo TEXT,
    correlativo INTEGER,
    codigo_producto TEXT,
    codigo_categoria TEXT,
    categoria TEXT,
    rubro TEXT,
    familia TEXT,
    nombre_producto TEXT,
    descripcion TEXT,
    unidad_medida TEXT,
    cantidad REAL,
    rut_proveedor TEXT,
    proveedor TEXT,
    cantidad_adjudicada REAL,
    monto_unitario REAL,
    PRIMARY KEY (codigo, correlativo)
);
CREATE INDEX IF NOT EXISTS ix_lic_estado ON licitaciones(estado_codigo);
CREATE INDEX IF NOT EXISTS ix_lic_region ON licitaciones(region);
CREATE INDEX IF NOT EXISTS ix_items_rubro ON items(rubro);
CREATE INDEX IF NOT EXISTS ix_items_familia ON items(familia);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def set_meta(con, clave: str, valor: str):
    con.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES (?, ?)", (clave, valor))
    con.commit()


def get_meta(con, clave: str, default=None):
    row = con.execute("SELECT valor FROM meta WHERE clave = ?", (clave,)).fetchone()
    return row["valor"] if row else default


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _niveles(categoria: str | None) -> tuple[str | None, str | None]:
    """'Segmento / Familia / Clase' -> (segmento, 'Segmento / Familia')."""
    if not categoria:
        return None, None
    partes = [p.strip() for p in categoria.split("/") if p.strip()]
    if not partes:
        return None, None
    return partes[0], " / ".join(partes[:2])


def upsert_resumen(con, item: dict):
    """Guarda una fila del listado resumido sin pisar el detalle ya cargado."""
    con.execute(
        """INSERT INTO licitaciones(codigo, nombre, estado_codigo, fecha_cierre, actualizado)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(codigo) DO UPDATE SET
             nombre = excluded.nombre,
             estado_codigo = excluded.estado_codigo,
             fecha_cierre = COALESCE(excluded.fecha_cierre, licitaciones.fecha_cierre),
             detalle_cargado = CASE WHEN licitaciones.estado_codigo IS excluded.estado_codigo
                                    THEN licitaciones.detalle_cargado ELSE 0 END,
             actualizado = excluded.actualizado""",
        (
            item.get("CodigoExterno"),
            item.get("Nombre"),
            item.get("CodigoEstado"),
            item.get("FechaCierre"),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def upsert_detalle(con, d: dict):
    comprador = d.get("Comprador") or {}
    fechas = d.get("Fechas") or {}
    adj = d.get("Adjudicacion") or {}
    codigo = d.get("CodigoExterno")
    con.execute(
        """INSERT OR REPLACE INTO licitaciones(
             codigo, nombre, descripcion, estado_codigo, tipo, moneda, monto_estimado,
             organismo_codigo, organismo, unidad, region, comuna,
             fecha_publicacion, fecha_cierre, fecha_adjudicacion, num_oferentes, url_acta,
             detalle_cargado, raw, actualizado)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
        (
            codigo,
            d.get("Nombre"),
            d.get("Descripcion"),
            d.get("CodigoEstado"),
            d.get("Tipo"),
            d.get("Moneda"),
            _num(d.get("MontoEstimado")),
            str(comprador.get("CodigoOrganismo") or ""),
            comprador.get("NombreOrganismo"),
            comprador.get("NombreUnidad"),
            (comprador.get("RegionUnidad") or "").strip() or None,
            (comprador.get("ComunaUnidad") or "").strip() or None,
            fechas.get("FechaPublicacion"),
            fechas.get("FechaCierre") or d.get("FechaCierre"),
            fechas.get("FechaAdjudicacion") or adj.get("Fecha"),
            int(adj["NumeroOferentes"]) if adj.get("NumeroOferentes") not in (None, "") else None,
            adj.get("UrlActa"),
            json.dumps(d, ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    con.execute("DELETE FROM items WHERE codigo = ?", (codigo,))
    for it in ((d.get("Items") or {}).get("Listado") or []):
        rubro, familia = _niveles(it.get("Categoria"))
        a = it.get("Adjudicacion") or {}
        con.execute(
            """INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                codigo,
                it.get("Correlativo"),
                str(it.get("CodigoProducto") or ""),
                str(it.get("CodigoCategoria") or ""),
                it.get("Categoria"),
                rubro,
                familia,
                it.get("NombreProducto"),
                it.get("Descripcion"),
                it.get("UnidadMedida"),
                _num(it.get("Cantidad")),
                a.get("RutProveedor"),
                a.get("NombreProveedor"),
                _num(a.get("Cantidad")),
                _num(a.get("MontoUnitario")),
            ),
        )


def estado_nombre(codigo) -> str:
    return ESTADOS.get(codigo, str(codigo) if codigo is not None else "")
