import json

import httpx
import pytest

from licitador import analysis, db, demo, sync
from licitador.api_client import MercadoPublicoClient, MercadoPublicoError


@pytest.fixture
def con(tmp_path):
    demo.generar(n=600, path=tmp_path / "t.db")
    return db.connect(tmp_path / "t.db")


def test_rubros_ordenados_y_en_rango(con):
    rs = analysis.analizar_rubros(con)
    assert rs
    assert [r["puntaje"] for r in rs] == sorted((r["puntaje"] for r in rs), reverse=True)
    assert all(0 <= r["puntaje"] <= 100 for r in rs)


def test_pesos_cambian_el_orden(con):
    solo_competencia = analysis.analizar_rubros(con, pesos={k: 0 for k in analysis.PESOS_DEFECTO} | {"competencia": 1})
    confiables = [r for r in solo_competencia if not r["pocos_datos"]]
    of = [r["oferentes_promedio"] for r in confiables[:3]]
    resto = [r["oferentes_promedio"] for r in confiables[3:] if r["oferentes_promedio"]]
    assert max(of) <= max(resto)


def test_oportunidades_abiertas_solo_publicadas(con):
    for o in analysis.oportunidades_abiertas(con):
        estado = con.execute("SELECT estado_codigo FROM licitaciones WHERE codigo = ?", (o["codigo"],)).fetchone()[0]
        assert estado == 5


DETALLE = {
    "CodigoExterno": "1234-5-LE26", "Nombre": "Compra de notebooks", "CodigoEstado": 8,
    "Comprador": {"CodigoOrganismo": "1234", "NombreOrganismo": "Municipalidad X", "RegionUnidad": "Región de Valparaíso "},
    "Tipo": "LE", "MontoEstimado": "15000000",
    "Fechas": {"FechaPublicacion": "2026-09-01T10:00:00", "FechaCierre": "2026-09-10T15:00:00"},
    "Adjudicacion": {"NumeroOferentes": 3},
    "Items": {"Listado": [{"Correlativo": 1, "CodigoCategoria": 43211503,
                           "Categoria": "Equipos informáticos y accesorios / Computadores / Notebooks",
                           "NombreProducto": "Notebook", "Cantidad": 10,
                           "Adjudicacion": {"RutProveedor": "76.111.111-1", "NombreProveedor": "Proveedor SpA",
                                            "Cantidad": 10, "MontoUnitario": 900000}}]},
}


def _cliente(manejador):
    return MercadoPublicoClient(ticket="T", delay=0, transport=httpx.MockTransport(manejador))


def test_sync_con_api_simulada(tmp_path):
    def manejador(req):
        q = req.url.params
        assert q["ticket"] == "T"
        if "codigo" in q:
            return httpx.Response(200, json={"Cantidad": 1, "Listado": [DETALLE]})
        return httpx.Response(200, json={"Cantidad": 1, "Listado": [
            {"CodigoExterno": "1234-5-LE26", "Nombre": "Compra de notebooks", "CodigoEstado": 8, "FechaCierre": None}]})
    con = db.connect(tmp_path / "s.db")
    sync.sync_historico(con, _cliente(manejador), dias=2, estados=("adjudicada",))
    lic = con.execute("SELECT * FROM licitaciones").fetchone()
    assert lic["detalle_cargado"] == 1 and lic["num_oferentes"] == 3 and lic["region"] == "Región de Valparaíso"
    it = con.execute("SELECT * FROM items").fetchone()
    assert it["rubro"] == "Equipos informáticos y accesorios"
    assert it["familia"] == "Equipos informáticos y accesorios / Computadores"
    r = analysis.analizar_rubros(con)[0]
    assert r["monto_total"] == 9_000_000 and r["oferentes_promedio"] == 3


def test_reintenta_peticiones_simultaneas(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    llamadas = []
    def manejador(req):
        llamadas.append(1)
        if len(llamadas) == 1:
            return httpx.Response(500, json={"Codigo": 10500, "Mensaje": "Peticiones simultáneas"})
        return httpx.Response(200, json={"Listado": []})
    assert _cliente(manejador).listar(estado="activas") == []
    assert len(llamadas) == 2


def test_ticket_invalido():
    c = _cliente(lambda req: httpx.Response(200, json={"Codigo": 203, "Mensaje": "Ticket no válido."}))
    with pytest.raises(MercadoPublicoError, match="Ticket"):
        c.listar(estado="activas")
