"""Análisis de oportunidades por rubro.

Para cada rubro (segmento ONU/UNSPSC de los ítems, o familia si se pide más
detalle) se calculan indicadores de competencia, demanda y concentración a
partir de las licitaciones ya cerradas, y se combinan en un puntaje 0-100 de
"factibilidad de participar y adjudicar". Cada indicador se transforma a
percentil entre rubros, así ningún indicador domina por su escala.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

NIVELES = {"rubro": "i.rubro", "familia": "i.familia"}

PESOS_DEFECTO = {
    "competencia": 0.35,   # pocos oferentes por licitación
    "apertura": 0.20,      # mercado poco concentrado en un proveedor
    "demanda": 0.20,       # cantidad de licitaciones
    "monto": 0.10,         # monto adjudicado promedio
    "compradores": 0.10,   # cantidad de organismos distintos que compran
    "accesibilidad": 0.05, # proporción de licitaciones pequeñas (L1/LE)
}

TIPOS_PEQUENOS = {"L1", "LE", "E2"}
MIN_CERRADAS = 5  # bajo esto el rubro se marca con pocos datos


def _filtros(region=None, dias=None, monto_max=None, organismo=None):
    where, params = [], []
    if region:
        where.append("l.region = ?")
        params.append(region)
    if dias:
        desde = (datetime.now() - timedelta(days=int(dias))).isoformat(timespec="seconds")
        where.append("COALESCE(l.fecha_publicacion, l.fecha_cierre) >= ?")
        params.append(desde)
    if monto_max:
        where.append("(l.monto_estimado IS NULL OR l.monto_estimado <= ?)")
        params.append(float(monto_max))
    if organismo:
        where.append("l.organismo_codigo = ?")
        params.append(organismo)
    return where, params


def _percentiles(valores: dict[str, float], mayor_es_mejor=True) -> dict[str, float]:
    """Percentil (0..1) de cada clave, con empates promediados."""
    claves = [k for k, v in valores.items() if v is not None]
    if not claves:
        return {}
    if len(claves) == 1:
        return {claves[0]: 0.5}
    orden = sorted(claves, key=lambda k: valores[k], reverse=not mayor_es_mejor)
    pos: dict[float, list[int]] = defaultdict(list)
    for i, k in enumerate(orden):
        pos[valores[k]].append(i)
    n = len(orden) - 1
    return {k: mean(pos[valores[k]]) / n for k in claves}


def _fmt_monto(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:,.1f} mil millones".replace(",", "X").replace(".", ",").replace("X", ".")
    if v >= 1e6:
        return f"${v/1e6:,.1f} millones".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${v:,.0f}".replace(",", ".")


def analizar_rubros(con, nivel="rubro", region=None, dias=None, monto_max=None,
                    pesos: dict | None = None, min_licitaciones: int = 1) -> list[dict]:
    col = NIVELES.get(nivel, "i.rubro")
    where, params = _filtros(region, dias, monto_max)
    where.append(f"{col} IS NOT NULL")
    w = " AND ".join(where)

    filas = con.execute(
        f"""SELECT {col} AS rubro, l.codigo, l.estado_codigo, l.num_oferentes,
                   l.organismo_codigo, l.tipo,
                   SUM(i.cantidad_adjudicada * i.monto_unitario) AS monto_adj
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w}
            GROUP BY rubro, l.codigo""",
        params,
    ).fetchall()

    ganadores = con.execute(
        f"""SELECT {col} AS rubro, i.rut_proveedor AS rut, MAX(i.proveedor) AS nombre,
                   COUNT(DISTINCT i.codigo) AS ganadas,
                   SUM(i.cantidad_adjudicada * i.monto_unitario) AS monto
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w} AND i.rut_proveedor IS NOT NULL
            GROUP BY rubro, i.rut_proveedor""",
        params,
    ).fetchall()

    acc: dict[str, dict] = defaultdict(lambda: {
        "licitaciones": 0, "activas": 0, "adjudicadas": 0, "desiertas": 0,
        "oferentes": [], "montos": [], "compradores": set(), "pequenas": 0, "con_tipo": 0,
    })
    for f in filas:
        a = acc[f["rubro"]]
        a["licitaciones"] += 1
        e = f["estado_codigo"]
        if e == 5:
            a["activas"] += 1
        elif e == 8:
            a["adjudicadas"] += 1
            if f["num_oferentes"]:
                a["oferentes"].append(f["num_oferentes"])
            if f["monto_adj"]:
                a["montos"].append(f["monto_adj"])
        elif e == 7:
            a["desiertas"] += 1
        if f["organismo_codigo"]:
            a["compradores"].add(f["organismo_codigo"])
        if f["tipo"]:
            a["con_tipo"] += 1
            if f["tipo"] in TIPOS_PEQUENOS:
                a["pequenas"] += 1

    prov: dict[str, list] = defaultdict(list)
    for g in ganadores:
        prov[g["rubro"]].append(g)

    res = []
    for rubro, a in acc.items():
        if a["licitaciones"] < min_licitaciones:
            continue
        cerradas = a["adjudicadas"] + a["desiertas"]
        ps = prov.get(rubro, [])
        total_monto = sum(p["monto"] or 0 for p in ps)
        total_gan = sum(p["ganadas"] for p in ps)
        if total_monto > 0:
            cuotas = [(p["monto"] or 0) / total_monto for p in ps]
        elif total_gan > 0:
            cuotas = [p["ganadas"] / total_gan for p in ps]
        else:
            cuotas = []
        top = sorted(ps, key=lambda p: (p["monto"] or 0, p["ganadas"]), reverse=True)[:5]
        of = mean(a["oferentes"]) if a["oferentes"] else None
        res.append({
            "rubro": rubro,
            "licitaciones": a["licitaciones"],
            "activas": a["activas"],
            "adjudicadas": a["adjudicadas"],
            "desiertas": a["desiertas"],
            "tasa_desierta": a["desiertas"] / cerradas if cerradas else None,
            "oferentes_promedio": of,
            "prob_base": min(1.0, 1 / of) if of else None,
            "monto_total": sum(a["montos"]),
            "monto_promedio": mean(a["montos"]) if a["montos"] else None,
            "compradores": len(a["compradores"]),
            "proveedores": len(ps),
            "cuota_lider": max(cuotas) if cuotas else None,
            "hhi": sum(c * c for c in cuotas) if cuotas else None,
            "pct_pequenas": a["pequenas"] / a["con_tipo"] if a["con_tipo"] else None,
            "pocos_datos": cerradas < MIN_CERRADAS,
            "top_proveedores": [
                {"rut": p["rut"], "nombre": p["nombre"], "ganadas": p["ganadas"], "monto": p["monto"]}
                for p in top
            ],
        })

    _puntuar(res, pesos)
    res.sort(key=lambda r: r["puntaje"], reverse=True)
    return res


def _puntuar(res: list[dict], pesos: dict | None):
    pesos = {**PESOS_DEFECTO, **(pesos or {})}
    total_peso = sum(max(0.0, v) for v in pesos.values()) or 1.0
    base = [r for r in res if not r["pocos_datos"]] or res
    def pct(campo, mayor_es_mejor=True, transf=lambda x: x):
        vals = {r["rubro"]: (transf(r[campo]) if r[campo] is not None else None) for r in base}
        p = _percentiles(vals, mayor_es_mejor)
        # Rubros fuera de la base (pocos datos) se ubican por interpolación.
        ordenados = sorted((v, p[k]) for k, v in vals.items() if v is not None)
        def ubicar(v):
            if v is None or not ordenados:
                return 0.5
            menores = [q for (x, q) in ordenados if (x <= v if mayor_es_mejor else x >= v)]
            return max(menores) if menores else 0.0
        return {r["rubro"]: p.get(r["rubro"], ubicar(transf(r[campo]) if r[campo] is not None else None)) for r in res}

    comp = pct("oferentes_promedio", mayor_es_mejor=False)
    aper = pct("cuota_lider", mayor_es_mejor=False)
    dem = pct("licitaciones", transf=math.log1p)
    mon = pct("monto_promedio", transf=math.log1p)
    compr = pct("compradores")
    acce = pct("pct_pequenas")
    for r in res:
        k = r["rubro"]
        comps = {
            "competencia": comp[k], "apertura": aper[k], "demanda": dem[k],
            "monto": mon[k], "compradores": compr[k], "accesibilidad": acce[k],
        }
        bruto = 100 * sum(max(0.0, pesos[c]) * v for c, v in comps.items()) / total_peso
        cerradas = r["adjudicadas"] + r["desiertas"]
        confianza = cerradas / (cerradas + MIN_CERRADAS)
        r["componentes"] = {c: round(v * 100) for c, v in comps.items()}
        r["confianza"] = round(confianza, 2)
        r["puntaje"] = round(50 + (bruto - 50) * confianza, 1)
        r["razones"] = _razones(r, comps)


def _razones(r: dict, comps: dict) -> list[str]:
    out = []
    of = r["oferentes_promedio"]
    if of is not None:
        if comps["competencia"] >= 0.66:
            out.append(f"Baja competencia: {of:.1f} oferentes por licitación en promedio".replace(".", ","))
        elif comps["competencia"] <= 0.33:
            out.append(f"Competencia alta: {of:.1f} oferentes por licitación".replace(".", ","))
    if r["cuota_lider"] is not None:
        c = round(r["cuota_lider"] * 100)
        if comps["apertura"] >= 0.66:
            out.append(f"Mercado abierto: el proveedor líder tiene {c}% de lo adjudicado")
        elif comps["apertura"] <= 0.33:
            nombre = r["top_proveedores"][0]["nombre"] if r["top_proveedores"] else "un proveedor"
            out.append(f"Concentrado: {nombre} tiene {c}% de lo adjudicado")
    if comps["demanda"] >= 0.66:
        out.append(f"Demanda alta: {r['licitaciones']} licitaciones en el período")
    if r["monto_promedio"] and comps["monto"] >= 0.66:
        out.append(f"Montos altos: {_fmt_monto(r['monto_promedio'])} adjudicados por licitación")
    if r["tasa_desierta"] and r["tasa_desierta"] >= 0.25:
        out.append(f"{round(r['tasa_desierta']*100)}% quedó desierta: oportunidad si se cumplen bien las bases")
    if r["activas"]:
        out.append(f"{r['activas']} licitaciones abiertas ahora")
    if r["pocos_datos"]:
        out.append("Pocos datos históricos: puntaje poco confiable")
    return out


def detalle_rubro(con, rubro: str, nivel="rubro", region=None, dias=None, monto_max=None) -> dict:
    col = NIVELES.get(nivel, "i.rubro")
    where, params = _filtros(region, dias, monto_max)
    where.append(f"{col} = ?")
    params.append(rubro)
    w = " AND ".join(where)
    proveedores = [dict(r) for r in con.execute(
        f"""SELECT i.rut_proveedor AS rut, MAX(i.proveedor) AS nombre,
                   COUNT(DISTINCT i.codigo) AS ganadas,
                   SUM(i.cantidad_adjudicada * i.monto_unitario) AS monto
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w} AND i.rut_proveedor IS NOT NULL
            GROUP BY i.rut_proveedor ORDER BY monto DESC LIMIT 15""", params)]
    compradores = [dict(r) for r in con.execute(
        f"""SELECT l.organismo_codigo AS codigo, MAX(l.organismo) AS nombre,
                   COUNT(DISTINCT l.codigo) AS licitaciones,
                   AVG(l.num_oferentes) AS oferentes_promedio
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w}
            GROUP BY l.organismo_codigo ORDER BY licitaciones DESC LIMIT 15""", params)]
    productos = [dict(r) for r in con.execute(
        f"""SELECT i.nombre_producto AS producto, COUNT(DISTINCT i.codigo) AS licitaciones
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w} GROUP BY i.nombre_producto ORDER BY licitaciones DESC LIMIT 10""", params)]
    por_mes = [dict(r) for r in con.execute(
        f"""SELECT substr(COALESCE(l.fecha_publicacion, l.fecha_cierre), 1, 7) AS mes,
                   COUNT(DISTINCT l.codigo) AS licitaciones
            FROM items i JOIN licitaciones l ON l.codigo = i.codigo
            WHERE {w} GROUP BY mes ORDER BY mes""", params)]
    activas = oportunidades_abiertas(con, region=region, rubro=rubro, nivel=nivel, limite=20)
    return {"rubro": rubro, "proveedores": proveedores, "compradores": compradores,
            "productos": productos, "por_mes": por_mes, "activas": activas}


def historial_organismo(con, organismo_codigo: str) -> dict:
    r = con.execute(
        """SELECT COUNT(*) AS licitaciones,
                  SUM(estado_codigo = 8) AS adjudicadas,
                  SUM(estado_codigo = 7) AS desiertas,
                  AVG(CASE WHEN estado_codigo = 8 THEN num_oferentes END) AS oferentes_promedio
           FROM licitaciones WHERE organismo_codigo = ?""", (organismo_codigo,)).fetchone()
    top = [dict(x) for x in con.execute(
        """SELECT i.rut_proveedor AS rut, MAX(i.proveedor) AS nombre,
                  COUNT(DISTINCT i.codigo) AS ganadas,
                  SUM(i.cantidad_adjudicada * i.monto_unitario) AS monto
           FROM items i JOIN licitaciones l ON l.codigo = i.codigo
           WHERE l.organismo_codigo = ? AND i.rut_proveedor IS NOT NULL
           GROUP BY i.rut_proveedor ORDER BY ganadas DESC, monto DESC LIMIT 5""",
        (organismo_codigo,))]
    return {**dict(r), "top_proveedores": top}


def oportunidades_abiertas(con, region=None, rubro=None, nivel="rubro", monto_max=None,
                           limite=50, puntajes: dict | None = None) -> list[dict]:
    """Licitaciones publicadas con cierre futuro, priorizadas por el puntaje de su rubro."""
    col = NIVELES.get(nivel, "i.rubro")
    ahora = datetime.now().isoformat(timespec="seconds")
    where = ["l.estado_codigo = 5", "l.detalle_cargado = 1", "(l.fecha_cierre IS NULL OR l.fecha_cierre >= ?)"]
    params: list = [ahora]
    if region:
        where.append("l.region = ?")
        params.append(region)
    if monto_max:
        where.append("(l.monto_estimado IS NULL OR l.monto_estimado <= ?)")
        params.append(float(monto_max))
    if rubro:
        where.append(f"{col} = ?")
        params.append(rubro)
    filas = con.execute(
        f"""SELECT l.codigo, l.nombre, l.organismo, l.organismo_codigo, l.region, l.tipo,
                   l.monto_estimado, l.fecha_cierre, GROUP_CONCAT(DISTINCT {col}) AS rubros
            FROM licitaciones l JOIN items i ON i.codigo = l.codigo
            WHERE {' AND '.join(where)}
            GROUP BY l.codigo""", params).fetchall()
    if puntajes is None:
        puntajes = {r["rubro"]: r["puntaje"] for r in analizar_rubros(con, nivel=nivel, region=region)}
    org_of = {r["organismo_codigo"]: r["of"] for r in con.execute(
        """SELECT organismo_codigo, AVG(num_oferentes) AS of FROM licitaciones
           WHERE estado_codigo = 8 AND num_oferentes IS NOT NULL GROUP BY organismo_codigo""")}
    out = []
    for f in filas:
        rubros = (f["rubros"] or "").split(",")
        p_rubro = max((puntajes.get(r, 50) for r in rubros), default=50)
        of = org_of.get(f["organismo_codigo"])
        # Ajuste por comprador: organismos que suelen recibir pocas ofertas suman puntos.
        ajuste = 0.0 if of is None else max(-10.0, min(10.0, (4 - of) * 3))
        dias = None
        if f["fecha_cierre"]:
            try:
                dias = (datetime.fromisoformat(f["fecha_cierre"][:19]) - datetime.now()).days
            except ValueError:
                pass
        out.append({**dict(f), "rubros": rubros, "puntaje": round(min(100, max(0, p_rubro + ajuste)), 1),
                    "oferentes_organismo": of, "dias_al_cierre": dias})
    out.sort(key=lambda r: r["puntaje"], reverse=True)
    return out[:limite]
