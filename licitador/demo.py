"""Genera datos de demostración con la misma estructura que la API.

Sirve para probar la aplicación sin ticket. Los datos son ficticios: los
organismos, proveedores y montos son inventados.

    python -m licitador.demo            # crea data/licitador.db con ~2.500 licitaciones
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import config, db

REGIONES = [
    "Región Metropolitana de Santiago", "Región de Valparaíso", "Región del Biobío",
    "Región de La Araucanía", "Región de Los Lagos", "Región de Antofagasta",
    "Región del Maule", "Región de Coquimbo", "Región de O'Higgins", "Región de Ñuble",
    "Región de Tarapacá", "Región de Atacama", "Región de Los Ríos", "Región de Arica y Parinacota",
    "Región de Aysén", "Región de Magallanes",
]

# (segmento, código, [(familia, productos)], peso, oferentes_medios, n_proveedores, zipf, monto_log_medio, p_desierta)
RUBROS = [
    ("Equipamiento y suministros médicos", "42",
     [("Productos para el cuidado de heridas", ["Apósitos", "Gasas estériles", "Vendas elásticas"]),
      ("Equipo médico de diagnóstico", ["Monitor multiparámetro", "Oxímetro de pulso", "Electrocardiógrafo"])],
     14, 6.5, 60, 1.1, 15.8, 0.10),
    ("Medicamentos y productos farmacéuticos", "51",
     [("Antiinfecciosos", ["Amoxicilina", "Ceftriaxona"]), ("Analgésicos", ["Paracetamol", "Ketoprofeno"])],
     10, 4.2, 25, 1.6, 16.2, 0.12),
    ("Alimentos, bebidas y tabaco", "50",
     [("Productos lácteos y huevos", ["Leche", "Queso"]), ("Frutas y verduras", ["Fruta fresca", "Verduras de temporada"])],
     8, 3.1, 70, 0.8, 15.0, 0.18),
    ("Servicios de construcción y mantenimiento", "72",
     [("Mantenimiento de edificios", ["Reparación de techumbre", "Pintura de fachada"]),
      ("Construcción de obras civiles", ["Mejoramiento de veredas", "Construcción de sede social"])],
     9, 2.4, 90, 0.6, 17.3, 0.28),
    ("Artículos para estructuras, obras y construcciones", "30",
     [("Materiales de construcción", ["Cemento", "Planchas de zinc", "Madera dimensionada"])],
     6, 3.6, 45, 1.0, 15.2, 0.15),
    ("Equipos y suministros de oficina", "44",
     [("Útiles de escritorio", ["Papel fotocopia", "Archivadores", "Lápices"]),
      ("Máquinas de oficina", ["Destructora de papel", "Plastificadora"])],
     9, 7.8, 40, 1.3, 13.6, 0.06),
    ("Equipos informáticos y accesorios", "43",
     [("Computadores", ["Notebook", "Computador de escritorio"]), ("Periféricos", ["Impresora", "Monitor"])],
     8, 8.9, 35, 1.5, 15.9, 0.07),
    ("Servicios de limpieza, descontaminación y tratamiento de residuos", "76",
     [("Servicios de aseo", ["Aseo de dependencias", "Retiro de residuos"])],
     5, 2.9, 30, 1.2, 16.8, 0.20),
    ("Servicios de transporte, almacenaje y correo", "78",
     [("Transporte de pasajeros", ["Transporte escolar", "Arriendo de buses"])],
     4, 2.2, 50, 0.7, 16.0, 0.32),
    ("Muebles, mobiliario y decoración", "56",
     [("Mobiliario de oficina", ["Sillas ergonómicas", "Escritorios"]), ("Mobiliario escolar", ["Mesas escolares"])],
     5, 5.5, 30, 1.1, 14.9, 0.10),
    ("Servicios de gestión, servicios profesionales de empresa y servicios administrativos", "80",
     [("Consultoría", ["Asesoría en gestión", "Estudio de diagnóstico"]), ("Capacitación", ["Curso de capacitación"])],
     6, 3.0, 80, 0.5, 15.7, 0.22),
    ("Equipos de limpieza y suministros", "47",
     [("Artículos de aseo", ["Detergente", "Papel higiénico", "Cloro"])],
     6, 6.2, 25, 1.4, 13.9, 0.05),
    ("Ropa, maletas y productos de aseo personal", "53",
     [("Vestuario institucional", ["Uniformes", "Calzado de seguridad"])],
     4, 4.8, 30, 1.0, 14.8, 0.12),
    ("Servicios educativos y de formación", "86",
     [("Talleres", ["Taller deportivo", "Taller artístico"])],
     3, 1.8, 60, 0.4, 14.5, 0.35),
    ("Equipos y suministros de laboratorio, de medición, de observación y de pruebas", "41",
     [("Reactivos", ["Reactivos de laboratorio clínico"]), ("Instrumentos", ["Balanza analítica"])],
     4, 2.6, 15, 1.8, 16.1, 0.14),
    ("Combustibles, aditivos para combustibles, lubricantes y anticorrosivos", "15",
     [("Combustibles", ["Petróleo diésel", "Gas licuado"])],
     2, 2.0, 6, 2.2, 16.5, 0.08),
    ("Equipos y suministros de defensa, orden público, protección, vigilancia y seguridad", "46",
     [("Seguridad", ["Cámaras de vigilancia", "Servicio de guardias"])],
     3, 3.4, 35, 0.9, 16.4, 0.18),
]

TIPOS_ORG = [
    ("Hospital", ["42", "51", "41", "47", "50", "76"]),
    ("Servicio de Salud", ["42", "51", "41", "80"]),
    ("Ilustre Municipalidad de", ["72", "30", "78", "86", "44", "47", "56", "46", "80"]),
    ("Universidad de", ["43", "44", "56", "80", "41", "72"]),
    ("Dirección Regional", ["44", "43", "78", "80", "53", "15"]),
    ("Servicio Local de Educación", ["56", "50", "78", "86", "44"]),
]
CIUDADES = {  # ciudad -> índice en REGIONES
    "Arica": 13, "Iquique": 10, "Antofagasta": 5, "Calama": 5, "Copiapó": 11, "La Serena": 7,
    "Valparaíso": 1, "Viña del Mar": 1, "Rancagua": 8, "Talca": 6, "Chillán": 9, "Concepción": 2,
    "Los Ángeles": 2, "Temuco": 3, "Angol": 3, "Valdivia": 12, "Puerto Montt": 4, "Osorno": 4,
    "Coyhaique": 14, "Punta Arenas": 15, "Santiago": 0, "Maipú": 0, "Puente Alto": 0, "La Florida": 0,
    "Ñuñoa": 0, "Peñalolén": 0,
}
PREF = ["Comercial", "Distribuidora", "Inversiones", "Servicios", "Ingeniería", "Sociedad", "Importadora", "Constructora"]
NOMBRES = ["Andes", "Pacífico", "del Sur", "Austral", "Cordillera", "Los Robles", "Araucaria", "Atacama",
           "Biobío", "Patagonia", "Maipo", "Aconcagua", "Valle Central", "Norte Grande", "Lago", "Volcán",
           "Altamira", "San Andrés", "Santa Elena", "Mirador"]
SUF = ["SpA", "Ltda.", "S.A.", "EIRL"]
UTM = 68000


def _rut(rng):
    n = rng.randint(76_000_000, 78_999_999)
    s, m = 0, 2
    for d in reversed(str(n)):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    dv = 11 - s % 11
    dv = {10: "K", 11: "0"}.get(dv, str(dv))
    return f"{n:,}".replace(",", ".") + f"-{dv}"


def _tipo_por_monto(monto):
    utm = monto / UTM
    if utm < 100:
        return "L1"
    if utm < 1000:
        return "LE"
    if utm < 2000:
        return "LP"
    if utm < 5000:
        return "LQ"
    return "LR"


def generar(n=2500, dias=120, seed=7, path=None):
    rng = random.Random(seed)
    con = db.connect(path or config.DB_PATH)
    con.executescript("DELETE FROM items; DELETE FROM licitaciones; DELETE FROM meta;")

    organismos = []
    for i in range(70):
        tipo, rubros = rng.choice(TIPOS_ORG)
        ciudad = rng.choice(list(CIUDADES))
        region = REGIONES[CIUDADES[ciudad]]
        organismos.append({"codigo": str(1000 + i * 37), "nombre": f"{tipo} {ciudad}",
                           "rubros": rubros, "region": region, "comuna": ciudad,
                           "dificultad": rng.uniform(0.7, 1.4)})

    proveedores = {}
    for seg in RUBROS:
        lista = []
        for _ in range(seg[5]):
            lista.append({"rut": _rut(rng),
                          "nombre": f"{rng.choice(PREF)} {rng.choice(NOMBRES)} {rng.choice(SUF)}"})
        proveedores[seg[1]] = lista

    por_codigo = {s[1]: s for s in RUBROS}
    ahora = datetime.now().replace(microsecond=0)
    seq = 0
    for _ in range(n):
        org = rng.choice(organismos)
        cod = rng.choice(org["rubros"]) if rng.random() < 0.85 else rng.choices(
            [s[1] for s in RUBROS], [s[3] for s in RUBROS])[0]
        seg = por_codigo[cod]
        nombre_seg, _, familias, _, of_medio, _, zipf, mlog, p_desierta = seg
        familia, productos = rng.choice(familias)
        pub = ahora - timedelta(days=rng.uniform(0, dias), hours=rng.randint(0, 23))
        pub = pub.replace(microsecond=0)
        cierre = pub + timedelta(days=rng.choice([5, 10, 10, 20, 30]))
        monto = round(rng.lognormvariate(mlog, 0.9), -3)
        tipo = _tipo_por_monto(monto)
        seq += 1
        codigo = f"{org['codigo']}-{seq}-{tipo}{str(pub.year)[2:]}"

        if cierre > ahora:
            estado = 5
        else:
            r = rng.random()
            estado = 7 if r < p_desierta else (18 if r < p_desierta + 0.03 else 8)
        n_items = rng.randint(1, 3)
        oferentes = None
        items = []
        ganador = None
        if estado == 8:
            oferentes = max(1, round(rng.gammavariate(2.0, of_medio * org["dificultad"] / 2.0)))
            pesos = [1 / (k + 1) ** zipf for k in range(len(proveedores[cod]))]
            ganador = rng.choices(proveedores[cod], pesos)[0]
        for k in range(n_items):
            producto = rng.choice(productos)
            cant = rng.randint(1, 200)
            adj = None
            if ganador:
                adj = {"RutProveedor": ganador["rut"], "NombreProveedor": ganador["nombre"],
                       "Cantidad": cant, "MontoUnitario": round(monto * rng.uniform(0.75, 1.0) / n_items / cant, 0)}
            items.append({
                "Correlativo": k + 1, "CodigoProducto": int(cod + "1" + str(rng.randint(100000, 999999))[:5]),
                "CodigoCategoria": int(cod + str(rng.randint(100000, 999999))), "Categoria":
                f"{nombre_seg} / {familia} / {producto}", "NombreProducto": producto,
                "Descripcion": f"{producto} según especificaciones técnicas", "UnidadMedida": "Unidad",
                "Cantidad": cant, "Adjudicacion": adj,
            })
        detalle = {
            "CodigoExterno": codigo,
            "Nombre": f"{rng.choice(['Adquisición de', 'Suministro de', 'Contratación de', 'Compra de'])} "
                      f"{familia.lower()} para {org['nombre']}",
            "CodigoEstado": estado,
            "Descripcion": f"{org['nombre']} requiere {', '.join(sorted({i['NombreProducto'].lower() for i in items}))}.",
            "FechaCierre": cierre.isoformat(),
            "Estado": db.estado_nombre(estado),
            "Comprador": {"CodigoOrganismo": org["codigo"], "NombreOrganismo": org["nombre"],
                          "NombreUnidad": "Abastecimiento", "ComunaUnidad": org["comuna"],
                          "RegionUnidad": org["region"]},
            "Tipo": tipo, "Moneda": "CLP", "MontoEstimado": monto,
            "Fechas": {"FechaPublicacion": pub.isoformat(), "FechaCierre": cierre.isoformat(),
                       "FechaAdjudicacion": (cierre + timedelta(days=rng.randint(5, 25))).isoformat() if estado == 8 else None},
            "Items": {"Cantidad": len(items), "Listado": items},
            "Adjudicacion": {"Tipo": 1, "Fecha": None, "NumeroOferentes": oferentes, "UrlActa": None} if estado == 8 else None,
        }
        db.upsert_detalle(con, detalle)
    db.set_meta(con, "demo", "1")
    con.commit()
    return n


if __name__ == "__main__":
    print(f"Generadas {generar()} licitaciones de demostración en {config.DB_PATH}")
