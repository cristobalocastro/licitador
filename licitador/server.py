"""Servidor web: API JSON + interfaz.

    uvicorn licitador.server:app --reload
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis, config, db, sync
from .api_client import ESTADOS, MercadoPublicoClient, MercadoPublicoError

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Licitador", version="0.1")
con = db.connect()
_lock = threading.Lock()  # sqlite3 compartido entre hilos
_sync_estado = {"corriendo": False, "mensajes": [], "error": None, "inicio": None, "fin": None}


def _q(sql, params=()):
    with _lock:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/estado")
def estado():
    r = _q("""SELECT COUNT(*) AS total, SUM(estado_codigo = 5) AS activas,
                     SUM(estado_codigo = 8) AS adjudicadas, SUM(detalle_cargado = 0) AS sin_detalle,
                     MIN(COALESCE(fecha_publicacion, fecha_cierre)) AS desde,
                     MAX(COALESCE(fecha_publicacion, fecha_cierre)) AS hasta
              FROM licitaciones""")[0]
    with _lock:
        demo = db.get_meta(con, "demo") == "1"
    return {**r, "demo": demo, "ticket_configurado": bool(config.TICKET), "sync": _sync_estado}


@app.get("/api/filtros")
def filtros():
    return {
        "regiones": [r["region"] for r in _q("SELECT DISTINCT region FROM licitaciones WHERE region IS NOT NULL ORDER BY region")],
        "rubros": [r["rubro"] for r in _q("SELECT DISTINCT rubro FROM items WHERE rubro IS NOT NULL ORDER BY rubro")],
        "estados": [{"codigo": k, "nombre": v} for k, v in ESTADOS.items()],
        "tipos": [r["tipo"] for r in _q("SELECT DISTINCT tipo FROM licitaciones WHERE tipo IS NOT NULL ORDER BY tipo")],
    }


@app.get("/api/licitaciones")
def buscar(texto: str | None = None, estado: int | None = None, region: str | None = None,
           rubro: str | None = None, organismo: str | None = None, tipo: str | None = None,
           monto_min: float | None = None, monto_max: float | None = None,
           abiertas: bool = False, orden: str = "cierre", pagina: int = 1,
           por_pagina: int = Query(25, le=200)):
    where, params = [], []
    if texto:
        for palabra in texto.split():
            where.append("""(l.nombre LIKE ? OR l.descripcion LIKE ? OR l.codigo LIKE ? OR l.organismo LIKE ?
                           OR EXISTS (SELECT 1 FROM items x WHERE x.codigo = l.codigo
                                      AND (x.nombre_producto LIKE ? OR x.descripcion LIKE ?)))""")
            params += [f"%{palabra}%"] * 6
    if estado is not None:
        where.append("l.estado_codigo = ?")
        params.append(estado)
    if abiertas:
        where.append("l.estado_codigo = 5 AND (l.fecha_cierre IS NULL OR l.fecha_cierre >= ?)")
        params.append(datetime.now().isoformat(timespec="seconds"))
    if region:
        where.append("l.region = ?")
        params.append(region)
    if rubro:
        where.append("EXISTS (SELECT 1 FROM items x WHERE x.codigo = l.codigo AND (x.rubro = ? OR x.familia = ?))")
        params += [rubro, rubro]
    if organismo:
        where.append("(l.organismo_codigo = ? OR l.organismo LIKE ?)")
        params += [organismo, f"%{organismo}%"]
    if tipo:
        where.append("l.tipo = ?")
        params.append(tipo)
    if monto_min is not None:
        where.append("l.monto_estimado >= ?")
        params.append(monto_min)
    if monto_max is not None:
        where.append("l.monto_estimado <= ?")
        params.append(monto_max)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    orden_sql = {
        "cierre": "l.fecha_cierre IS NULL, l.fecha_cierre ASC",
        "cierre_desc": "l.fecha_cierre DESC",
        "publicacion": "l.fecha_publicacion DESC",
        "monto": "l.monto_estimado IS NULL, l.monto_estimado DESC",
    }.get(orden, "l.fecha_cierre ASC")
    total = _q(f"SELECT COUNT(*) AS n FROM licitaciones l {w}", params)[0]["n"]
    filas = _q(
        f"""SELECT l.codigo, l.nombre, l.estado_codigo, l.tipo, l.monto_estimado, l.moneda,
                   l.organismo, l.region, l.fecha_publicacion, l.fecha_cierre, l.num_oferentes,
                   l.detalle_cargado,
                   (SELECT GROUP_CONCAT(DISTINCT x.rubro) FROM items x WHERE x.codigo = l.codigo) AS rubros
            FROM licitaciones l {w} ORDER BY {orden_sql} LIMIT ? OFFSET ?""",
        params + [por_pagina, (max(1, pagina) - 1) * por_pagina])
    for f in filas:
        f["estado"] = db.estado_nombre(f["estado_codigo"])
        f["rubros"] = f["rubros"].split(",") if f["rubros"] else []
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "resultados": filas}


@app.get("/api/licitaciones/{codigo}")
def licitacion(codigo: str, refrescar: bool = False):
    fila = _q("SELECT * FROM licitaciones WHERE codigo = ?", (codigo,))
    if (refrescar or not fila or not fila[0]["detalle_cargado"]) and config.TICKET:
        try:
            client = MercadoPublicoClient()
            d = client.detalle(codigo)
            client.close()
        except MercadoPublicoError as e:
            if not fila:
                raise HTTPException(502, str(e))
            d = None
        if d:
            with _lock:
                db.upsert_detalle(con, d)
                con.commit()
            fila = _q("SELECT * FROM licitaciones WHERE codigo = ?", (codigo,))
    if not fila:
        raise HTTPException(404, "Licitación no encontrada")
    lic = fila[0]
    raw = json.loads(lic.pop("raw") or "{}")
    lic["estado"] = db.estado_nombre(lic["estado_codigo"])
    lic["items"] = _q("SELECT * FROM items WHERE codigo = ? ORDER BY correlativo", (codigo,))
    lic["url_ficha"] = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"
    lic["fechas"] = raw.get("Fechas") or {}
    lic["contacto"] = {k: raw.get(k) for k in ("NombreResponsableContrato", "EmailResponsableContrato", "FonoResponsableContrato") if raw.get(k)}

    # Contexto para decidir si postular
    rubros = sorted({i["rubro"] for i in lic["items"] if i["rubro"]})
    with _lock:
        todos = {r["rubro"]: r for r in analysis.analizar_rubros(con)}
        org = analysis.historial_organismo(con, lic["organismo_codigo"]) if lic["organismo_codigo"] else None
    lic["analisis"] = {
        "rubros": [{k: todos[r][k] for k in ("rubro", "puntaje", "oferentes_promedio", "prob_base",
                                               "cuota_lider", "licitaciones", "razones", "top_proveedores")}
                   for r in rubros if r in todos],
        "organismo": org,
    }
    return lic


def _pesos(pesos: str | None) -> dict | None:
    if not pesos:
        return None
    try:
        return {k: float(v) for k, v in json.loads(pesos).items() if k in analysis.PESOS_DEFECTO}
    except (ValueError, AttributeError):
        raise HTTPException(400, "pesos debe ser un JSON {criterio: peso}")


@app.get("/api/oportunidades/rubros")
def rubros(nivel: str = "rubro", region: str | None = None, dias: int | None = None,
           monto_max: float | None = None, pesos: str | None = None):
    p = _pesos(pesos)
    with _lock:
        res = analysis.analizar_rubros(con, nivel, region, dias, monto_max, p)
    return {"pesos": {**analysis.PESOS_DEFECTO, **(p or {})}, "rubros": res}


@app.get("/api/oportunidades/rubro")
def rubro_detalle(rubro: str, nivel: str = "rubro", region: str | None = None,
                  dias: int | None = None, monto_max: float | None = None):
    with _lock:
        return analysis.detalle_rubro(con, rubro, nivel, region, dias, monto_max)


@app.get("/api/oportunidades/abiertas")
def abiertas(region: str | None = None, nivel: str = "rubro", monto_max: float | None = None,
             limite: int = 50, pesos: str | None = None):
    with _lock:
        puntajes = {r["rubro"]: r["puntaje"] for r in analysis.analizar_rubros(con, nivel, region, pesos=_pesos(pesos))}
        return analysis.oportunidades_abiertas(con, region=region, nivel=nivel, monto_max=monto_max,
                                               limite=limite, puntajes=puntajes)


class SyncPedido(BaseModel):
    tipo: str = "activas"  # activas | historico | detalles
    dias: int = 30
    maximo: int | None = None


@app.post("/api/sync")
def iniciar_sync(p: SyncPedido):
    if not config.TICKET:
        raise HTTPException(400, "Configura MP_TICKET con tu ticket de la API de Mercado Público y reinicia el servidor.")
    with _lock:
        if db.get_meta(con, "demo") == "1":
            raise HTTPException(409, "La base tiene datos de demostración. Bórrala (data/licitador.db) antes de sincronizar datos reales.")
    if _sync_estado["corriendo"]:
        raise HTTPException(409, "Ya hay una sincronización en curso")

    def log(msg):
        _sync_estado["mensajes"] = (_sync_estado["mensajes"] + [f"{datetime.now():%H:%M:%S} {msg}"])[-50:]

    def correr():
        # Conexión propia: la descarga es larga y no debe bloquear las consultas de la interfaz.
        c = db.connect()
        try:
            client = MercadoPublicoClient()
            if p.tipo == "historico":
                sync.sync_historico(c, client, p.dias, maximo_detalle=p.maximo, progreso=log)
            elif p.tipo == "detalles":
                sync.cargar_detalles(c, client, p.maximo, log)
            else:
                sync.sync_activas(c, client, p.maximo, log)
            log(f"Listo. Consultas a la API: {client.requests}")
            client.close()
        except Exception as e:  # se informa en la interfaz
            _sync_estado["error"] = str(e)
            log(f"Error: {e}")
        finally:
            c.close()
            _sync_estado["corriendo"] = False
            _sync_estado["fin"] = datetime.now().isoformat(timespec="seconds")

    _sync_estado.update(corriendo=True, mensajes=[], error=None,
                        inicio=datetime.now().isoformat(timespec="seconds"), fin=None)
    threading.Thread(target=correr, daemon=True).start()
    return {"ok": True}
