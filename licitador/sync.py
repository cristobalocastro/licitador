"""Descarga licitaciones desde la API y las guarda en la base local.

Uso:
    python -m licitador.sync activas            # licitaciones publicadas hoy en adelante
    python -m licitador.sync historico --dias 60  # adjudicadas y desiertas de los últimos 60 días
    python -m licitador.sync detalles --max 500   # completa el detalle pendiente

La API entrega un listado resumido; el detalle (ítems, rubros, comprador,
número de oferentes) requiere una consulta por licitación, por eso la
descarga del histórico puede tomar un buen rato. Un ticket permite del orden
de 10.000 consultas diarias.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Callable

from . import db
from .api_client import MercadoPublicoClient, MercadoPublicoError

Progreso = Callable[[str], None]


def _nada(_msg: str):
    pass


def cargar_detalles(con, client: MercadoPublicoClient, maximo: int | None = None,
                    progreso: Progreso = _nada, solo_activas: bool = False) -> int:
    sql = "SELECT codigo FROM licitaciones WHERE detalle_cargado = 0"
    if solo_activas:
        sql += " AND estado_codigo = 5"
    sql += " ORDER BY fecha_cierre DESC"
    if maximo:
        sql += f" LIMIT {int(maximo)}"
    codigos = [r["codigo"] for r in con.execute(sql)]
    hechos = 0
    for i, codigo in enumerate(codigos, 1):
        try:
            d = client.detalle(codigo)
        except MercadoPublicoError as e:
            progreso(f"[{i}/{len(codigos)}] {codigo}: {e}")
            if "ticket" in str(e).lower():
                raise
            continue
        if d:
            db.upsert_detalle(con, d)
            hechos += 1
        if i % 20 == 0 or i == len(codigos):
            con.commit()
            progreso(f"Detalle {i}/{len(codigos)}")
    con.commit()
    return hechos


def sync_activas(con, client: MercadoPublicoClient, maximo_detalle: int | None = None,
                 progreso: Progreso = _nada) -> int:
    progreso("Descargando licitaciones activas…")
    listado = client.listar(estado="activas")
    for it in listado:
        db.upsert_resumen(con, it)
    con.commit()
    progreso(f"{len(listado)} activas en el listado; cargando detalle…")
    cargar_detalles(con, client, maximo_detalle, progreso, solo_activas=True)
    db.set_meta(con, "ultima_sync_activas", date.today().isoformat())
    return len(listado)


def sync_historico(con, client: MercadoPublicoClient, dias: int = 30,
                   estados=("adjudicada", "desierta"), maximo_detalle: int | None = None,
                   progreso: Progreso = _nada) -> int:
    total = 0
    hoy = date.today()
    for n in range(1, dias + 1):
        dia = hoy - timedelta(days=n)
        for estado in estados:
            try:
                listado = client.listar(estado=estado, fecha=dia)
            except MercadoPublicoError as e:
                progreso(f"{dia} {estado}: {e}")
                if "ticket" in str(e).lower():
                    raise
                continue
            for it in listado:
                db.upsert_resumen(con, it)
            total += len(listado)
        con.commit()
        progreso(f"Listado {dia.isoformat()} ({n}/{dias}): {total} acumuladas")
    cargar_detalles(con, client, maximo_detalle, progreso)
    db.set_meta(con, "ultima_sync_historico", hoy.isoformat())
    return total


def main(argv=None):
    p = argparse.ArgumentParser(description="Sincroniza licitaciones de Mercado Público")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("activas")
    a.add_argument("--max", type=int, default=None, help="máximo de detalles a descargar")
    h = sub.add_parser("historico")
    h.add_argument("--dias", type=int, default=30)
    h.add_argument("--max", type=int, default=None)
    d = sub.add_parser("detalles")
    d.add_argument("--max", type=int, default=None)
    args = p.parse_args(argv)

    con = db.connect()
    if db.get_meta(con, "demo") == "1":
        print("La base actual tiene datos de demostración; bórrala (data/licitador.db) antes de sincronizar datos reales.")
        return 1
    client = MercadoPublicoClient()
    try:
        if args.cmd == "activas":
            sync_activas(con, client, args.max, print)
        elif args.cmd == "historico":
            sync_historico(con, client, args.dias, maximo_detalle=args.max, progreso=print)
        else:
            cargar_detalles(con, client, args.max, print)
    finally:
        print(f"Consultas a la API: {client.requests}")
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
