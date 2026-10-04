# Licitador

Busca y analiza licitaciones de **Mercado Público (ChileCompra)** y estima en qué rubros es más factible participar y adjudicar.

## Qué hace

- **Buscar licitaciones** por texto (nombre, producto, código u organismo), estado, región, rubro, tipo y monto. Cada ficha muestra los ítems, a quién se adjudicó y un bloque "¿Conviene postular?" con el historial del rubro y del comprador.
- **Oportunidades por rubro**: un puntaje 0-100 por rubro (segmento ONU de los ítems) o por familia, con las razones en palabras.
- **Licitaciones abiertas con mejor perspectiva**: las publicadas que aún no cierran, ordenadas por el puntaje de su rubro y por cuántas ofertas suele recibir el organismo comprador.
- **Sincronización** con la API oficial, guardando todo en una base SQLite local.

## Cómo se calcula el puntaje

Con las licitaciones ya cerradas del período elegido, por rubro:

| Criterio | Indicador | Peso por defecto |
|---|---|---|
| Pocos oferentes | oferentes promedio por licitación adjudicada (menos es mejor) | 35% |
| Mercado no concentrado | participación del proveedor líder en lo adjudicado (menos es mejor) | 20% |
| Cantidad de licitaciones | n.º de licitaciones del rubro | 20% |
| Monto promedio | monto adjudicado por licitación | 10% |
| Variedad de compradores | n.º de organismos distintos | 10% |
| Licitaciones pequeñas | proporción L1/LE, más accesibles para empresas pequeñas | 5% |

Cada indicador se convierte en percentil entre rubros y se ponderan. Los rubros con menos de 5 licitaciones cerradas se acercan a 50 (poca confianza). La **probabilidad base** es 1 / oferentes promedio: lo que ganarías si todos los oferentes tuvieran la misma chance. Los pesos se ajustan en la interfaz con "Ajustar criterios".

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Probar con datos de demostración (sin ticket)

```bash
python -m licitador.demo          # crea data/licitador.db con 2.500 licitaciones ficticias
uvicorn licitador.server:app --reload
```

Abre http://localhost:8000.

### Usar datos reales

1. Pide tu ticket gratis en https://api.mercadopublico.cl (ingresas con Clave Única).
2. Borra la base de demostración: `rm data/licitador.db`.
3. Define el ticket y descarga datos:

```bash
export MP_TICKET=TU-TICKET
python -m licitador.sync activas              # licitaciones abiertas hoy
python -m licitador.sync historico --dias 60  # adjudicadas y desiertas (para el análisis)
uvicorn licitador.server:app
```

También puedes sincronizar desde la pestaña **Datos** de la interfaz.

**Ojo con los límites de la API:** el listado diario trae solo código, nombre y estado; los rubros, montos y número de oferentes salen del detalle, que es una consulta por licitación. Con la pausa por defecto (0,6 s) son unas 1.000 licitaciones cada 10 minutos, y un ticket tiene un cupo diario (del orden de 10.000 consultas). Para un histórico grande, corre `historico` con `--max` varios días seguidos; `python -m licitador.sync detalles` completa lo pendiente.

## Variables de entorno

| Variable | Uso | Por defecto |
|---|---|---|
| `MP_TICKET` | ticket de la API | (vacío) |
| `LICITADOR_DB` | ruta de la base SQLite | `data/licitador.db` |
| `MP_REQUEST_DELAY` | segundos entre consultas | `0.6` |

## Estructura

```
licitador/
  api_client.py   cliente de la API (reintentos, límite de concurrencia)
  sync.py         descarga a SQLite (CLI)
  db.py           esquema y guardado
  analysis.py     indicadores y puntaje por rubro
  server.py       API JSON (FastAPI) + interfaz
  demo.py         datos ficticios para probar
  static/         interfaz web (HTML/CSS/JS sin dependencias)
tests/            pytest, incluye una API simulada
```

## Tests

```bash
pip install pytest && pytest -q
```
