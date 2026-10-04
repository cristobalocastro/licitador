const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = new Intl.NumberFormat("es-CL");
const nf1 = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function clp(v) {
  if (v == null) return "—";
  if (v >= 1e9) return "$" + nf1.format(v / 1e9) + " MM";
  if (v >= 1e6) return "$" + nf1.format(v / 1e6) + " M";
  return "$" + nf.format(Math.round(v));
}
const pct = (v) => (v == null ? "—" : Math.round(v * 100) + "%");
const fecha = (s) => (s ? new Date(s).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const pill = (cod, nombre) => `<span class="pill e${cod}">${esc(nombre)}</span>`;
const scoreBar = (v) => `<div class="score"><div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, v))}%"></div></div><b>${Math.round(v)}</b></div>`;

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null && v !== false)).toString();

// ---------- Tabs ----------
$$(".tab").forEach((b) => b.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.toggle("active", x === b));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "buscar" && !$("#b-tabla").innerHTML) buscar(1);
  if (b.dataset.tab === "datos") cargarEstado();
}));

// ---------- Tooltip ----------
const tip = $("#tooltip");
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.hidden = false;
  const x = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
const hideTip = () => (tip.hidden = true);

// ---------- Oportunidades ----------
const CRITERIOS = {
  competencia: "Pocos oferentes",
  apertura: "Mercado no concentrado",
  demanda: "Cantidad de licitaciones",
  monto: "Monto promedio",
  compradores: "Variedad de compradores",
  accesibilidad: "Licitaciones pequeñas (L1/LE)",
};
let pesos = null;

function filtrosOp() {
  return {
    nivel: $("#op-nivel").value,
    region: $("#op-region").value,
    dias: $("#op-dias").value,
    monto_max: $("#op-monto").value,
    pesos: pesos ? JSON.stringify(pesos) : "",
  };
}

async function cargarOportunidades() {
  const f = filtrosOp();
  $("#op-tabla").innerHTML = `<tr><td class="empty">Calculando…</td></tr>`;
  const [r, ab] = await Promise.all([
    api("/api/oportunidades/rubros?" + qs(f)),
    api("/api/oportunidades/abiertas?" + qs({ region: f.region, nivel: f.nivel, monto_max: f.monto_max, pesos: f.pesos, limite: 30 })),
  ]);
  if (!pesos) renderPesos(r.pesos);
  renderRubros(r.rubros);
  renderScatter(r.rubros);
  renderAbiertas(ab);
}

function renderPesos(p) {
  pesos = { ...p };
  $("#op-pesos").innerHTML = Object.entries(CRITERIOS).map(([k, label]) =>
    `<label>${label} <span id="pv-${k}">${Math.round(p[k] * 100)}</span>
       <input type="range" min="0" max="100" value="${Math.round(p[k] * 100)}" data-peso="${k}"></label>`).join("");
  $$("[data-peso]").forEach((i) => {
    i.addEventListener("input", () => ($("#pv-" + i.dataset.peso).textContent = i.value));
    i.addEventListener("change", () => { pesos[i.dataset.peso] = i.value / 100; cargarOportunidades(); });
  });
}
$("#op-pesos-btn").addEventListener("click", () => ($("#op-pesos").hidden = !$("#op-pesos").hidden));
["#op-nivel", "#op-region", "#op-dias", "#op-monto"].forEach((s) => $(s).addEventListener("change", cargarOportunidades));

function renderRubros(rubros) {
  if (!rubros.length) {
    $("#op-tabla").innerHTML = `<tr><td class="empty">Sin datos para estos filtros. Sincroniza el histórico en la pestaña Datos.</td></tr>`;
    return;
  }
  $("#op-tabla").innerHTML = `<thead><tr><th>Rubro</th><th>Puntaje</th><th class="num">Licitaciones</th>
      <th class="num">Oferentes prom.</th><th class="num">Prob. base</th><th class="num">Cuota líder</th><th class="num">Abiertas</th></tr></thead><tbody>` +
    rubros.map((r, i) => `<tr class="click" data-i="${i}">
      <td><b>${esc(r.rubro)}</b>${r.pocos_datos ? ' <span class="pill">pocos datos</span>' : ""}
        <ul class="razones">${r.razones.slice(0, 2).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></td>
      <td>${scoreBar(r.puntaje)}</td>
      <td class="num">${nf.format(r.licitaciones)}</td>
      <td class="num">${r.oferentes_promedio == null ? "—" : nf1.format(r.oferentes_promedio)}</td>
      <td class="num">${pct(r.prob_base)}</td>
      <td class="num">${pct(r.cuota_lider)}</td>
      <td class="num">${r.activas}</td></tr>`).join("") + "</tbody>";
  $$("#op-tabla tr.click").forEach((tr) => tr.addEventListener("click", () => abrirRubro(rubros[tr.dataset.i])));
}

function renderScatter(rubros) {
  const pts = rubros.filter((r) => r.oferentes_promedio != null);
  const el = $("#op-scatter");
  if (!pts.length) { el.innerHTML = `<div class="empty">Sin datos</div>`; return; }
  const W = 560, H = 380, m = { l: 48, r: 16, t: 12, b: 40 };
  const xmax = Math.ceil(Math.max(...pts.map((p) => p.oferentes_promedio)) + 0.5);
  const ymax = Math.max(...pts.map((p) => p.licitaciones)) * 1.1;
  const mmax = Math.max(...pts.map((p) => p.monto_promedio || 0)) || 1;
  const X = (v) => m.l + (v / xmax) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const R = (v) => 5 + 13 * Math.sqrt((v || 0) / mmax);
  const yticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * ymax));
  const xticks = Array.from({ length: xmax + 1 }, (_, i) => i).filter((i) => xmax <= 10 || i % 2 === 0);
  const top = new Set(pts.slice().sort((a, b) => b.puntaje - a.puntaje).slice(0, 4).map((p) => p.rubro));
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Oferentes promedio versus número de licitaciones por rubro">
    <g class="grid">${yticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"/>`).join("")}</g>
    <g class="axis">
      ${yticks.map((t) => `<text x="${m.l - 6}" y="${Y(t) + 4}" text-anchor="end">${nf.format(t)}</text>`).join("")}
      ${xticks.map((t) => `<text x="${X(t)}" y="${H - m.b + 16}" text-anchor="middle">${t}</text>`).join("")}
      <text x="${(W + m.l) / 2}" y="${H - 6}" text-anchor="middle">Oferentes promedio por licitación</text>
      <text transform="translate(12 ${(H - m.b) / 2}) rotate(-90)" text-anchor="middle">Licitaciones</text>
    </g>
    ${pts.map((p, i) => `<circle data-i="${i}" cx="${X(p.oferentes_promedio)}" cy="${Y(p.licitaciones)}" r="${R(p.monto_promedio)}"/>`).join("")}
    ${pts.filter((p) => top.has(p.rubro)).map((p) => `<text class="lbl" x="${X(p.oferentes_promedio) + R(p.monto_promedio) + 4}" y="${Y(p.licitaciones) + 4}">${esc(p.rubro.length > 28 ? p.rubro.slice(0, 27) + "…" : p.rubro)}</text>`).join("")}
  </svg>`;
  $$("circle", el).forEach((c) => {
    const p = pts[c.dataset.i];
    c.addEventListener("mousemove", (ev) => showTip(`<b>${esc(p.rubro)}</b><br>Puntaje ${Math.round(p.puntaje)}<br>
      ${nf.format(p.licitaciones)} licitaciones · ${nf1.format(p.oferentes_promedio)} oferentes prom.<br>Monto prom. ${clp(p.monto_promedio)}`, ev));
    c.addEventListener("mouseleave", hideTip);
    c.addEventListener("click", () => abrirRubro(p));
  });
}

function filaAbierta(o) {
  return `<tr class="click" data-cod="${esc(o.codigo)}">
    <td>${scoreBar(o.puntaje)}</td>
    <td><b>${esc(o.nombre)}</b><div class="small">${esc(o.codigo)} · ${esc(o.organismo)} · ${esc(o.region || "")}</div>
        <div class="small">${o.rubros.map(esc).join(" · ")}</div></td>
    <td class="num">${clp(o.monto_estimado)}</td>
    <td class="num">${o.oferentes_organismo == null ? "—" : nf1.format(o.oferentes_organismo)}</td>
    <td class="num">${fecha(o.fecha_cierre)}<div class="small">${o.dias_al_cierre != null ? `en ${o.dias_al_cierre} días` : ""}</div></td></tr>`;
}
const cabAbiertas = `<thead><tr><th>Puntaje</th><th>Licitación</th><th class="num">Monto est.</th><th class="num">Oferentes hab. del comprador</th><th class="num">Cierre</th></tr></thead>`;

function renderAbiertas(lista, sel = "#op-abiertas") {
  const t = $(sel);
  if (!lista.length) { t.innerHTML = `<tr><td class="empty">No hay licitaciones abiertas con detalle cargado.</td></tr>`; return; }
  t.innerHTML = cabAbiertas + "<tbody>" + lista.map(filaAbierta).join("") + "</tbody>";
  $$("tr.click", t).forEach((tr) => tr.addEventListener("click", () => abrirLicitacion(tr.dataset.cod)));
}

async function abrirRubro(r) {
  const f = filtrosOp();
  const d = await api("/api/oportunidades/rubro?" + qs({ rubro: r.rubro, nivel: f.nivel, region: f.region, dias: f.dias, monto_max: f.monto_max }));
  const totalMonto = d.proveedores.reduce((s, p) => s + (p.monto || 0), 0) || 1;
  $("#modal-body").innerHTML = `
    <h2>${esc(r.rubro)}</h2>
    <div class="kv">
      <div><span>Puntaje</span>${scoreBar(r.puntaje)}</div>
      <div><span>Licitaciones</span>${nf.format(r.licitaciones)} (${r.adjudicadas} adjudicadas, ${r.desiertas} desiertas)</div>
      <div><span>Oferentes promedio</span>${r.oferentes_promedio == null ? "—" : nf1.format(r.oferentes_promedio)} · prob. base ${pct(r.prob_base)}</div>
      <div><span>Monto total adjudicado</span>${clp(r.monto_total)}</div>
      <div><span>Proveedores ganadores</span>${r.proveedores} · líder ${pct(r.cuota_lider)}</div>
      <div><span>Organismos compradores</span>${r.compradores}</div>
    </div>
    <ul class="razones">${r.razones.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <h3>Componentes del puntaje (percentil entre rubros)</h3>
    <div class="kv">${Object.entries(CRITERIOS).map(([k, l]) => `<div><span>${l}</span>${scoreBar(r.componentes[k])}</div>`).join("")}</div>
    <div class="cols">
      <div><h3>Principales proveedores (competencia)</h3><table class="tbl"><thead><tr><th>Proveedor</th><th class="num">Ganadas</th><th class="num">Cuota</th></tr></thead><tbody>
        ${d.proveedores.map((p) => `<tr><td>${esc(p.nombre)}<div class="small">${esc(p.rut)}</div></td><td class="num">${p.ganadas}</td><td class="num">${pct((p.monto || 0) / totalMonto)}</td></tr>`).join("") || '<tr><td class="empty">Sin adjudicaciones</td></tr>'}
      </tbody></table></div>
      <div><h3>Principales compradores</h3><table class="tbl"><thead><tr><th>Organismo</th><th class="num">Licitaciones</th><th class="num">Oferentes prom.</th></tr></thead><tbody>
        ${d.compradores.map((c) => `<tr><td>${esc(c.nombre)}</td><td class="num">${c.licitaciones}</td><td class="num">${c.oferentes_promedio == null ? "—" : nf1.format(c.oferentes_promedio)}</td></tr>`).join("")}
      </tbody></table></div>
    </div>
    <h3>Productos más pedidos</h3>
    <p class="small">${d.productos.map((p) => `${esc(p.producto)} (${p.licitaciones})`).join(" · ")}</p>
    <h3>Licitaciones abiertas en este rubro</h3>
    <div class="table-wrap"><table id="m-abiertas" class="tbl"></table></div>`;
  renderAbiertas(d.activas, "#m-abiertas");
  $("#modal").showModal();
}

// ---------- Detalle de licitación ----------
async function abrirLicitacion(codigo) {
  $("#modal-body").innerHTML = `<p class="empty">Cargando ${esc(codigo)}…</p>`;
  if (!$("#modal").open) $("#modal").showModal();
  let l;
  try { l = await api("/api/licitaciones/" + encodeURIComponent(codigo)); }
  catch (e) { $("#modal-body").innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  const org = l.analisis.organismo;
  $("#modal-body").innerHTML = `
    <h2>${esc(l.nombre)}</h2>
    <div class="small">${esc(l.codigo)} · ${pill(l.estado_codigo, l.estado)} · <a href="${l.url_ficha}" target="_blank" rel="noopener">Ver ficha en Mercado Público</a></div>
    <div class="kv">
      <div><span>Organismo</span>${esc(l.organismo)}</div>
      <div><span>Región / comuna</span>${esc(l.region || "—")} / ${esc(l.comuna || "—")}</div>
      <div><span>Tipo</span>${esc(l.tipo || "—")}</div>
      <div><span>Monto estimado</span>${clp(l.monto_estimado)} ${esc(l.moneda || "")}</div>
      <div><span>Publicación</span>${fecha(l.fecha_publicacion)}</div>
      <div><span>Cierre</span>${fecha(l.fecha_cierre)}</div>
      ${l.num_oferentes != null ? `<div><span>Oferentes</span>${l.num_oferentes}</div>` : ""}
    </div>
    <p>${esc(l.descripcion || "")}</p>
    <h3>Ítems</h3>
    <div class="table-wrap"><table class="tbl"><thead><tr><th>#</th><th>Producto</th><th>Rubro</th><th class="num">Cantidad</th><th>Adjudicado a</th><th class="num">Monto</th></tr></thead><tbody>
      ${l.items.map((i) => `<tr><td>${i.correlativo}</td><td>${esc(i.nombre_producto)}<div class="small">${esc(i.descripcion || "")}</div></td>
        <td class="small">${esc(i.familia || i.categoria || "")}</td><td class="num">${nf.format(i.cantidad || 0)} ${esc(i.unidad_medida || "")}</td>
        <td>${esc(i.proveedor || "—")}</td><td class="num">${i.monto_unitario != null ? clp(i.monto_unitario * (i.cantidad_adjudicada || 0)) : "—"}</td></tr>`).join("")}
    </tbody></table></div>
    <h3>¿Conviene postular?</h3>
    <div class="cols">
      <div>${l.analisis.rubros.map((r) => `<p><b>${esc(r.rubro)}</b></p>${scoreBar(r.puntaje)}
        <ul class="razones">${r.razones.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <p class="small">Competidores frecuentes: ${r.top_proveedores.slice(0, 3).map((p) => esc(p.nombre)).join(", ") || "—"}</p>`).join("") || '<p class="empty">Sin histórico del rubro</p>'}</div>
      <div>${org ? `<p><b>Historial del comprador</b></p>
        <p class="small">${org.licitaciones} licitaciones en la base · ${org.adjudicadas || 0} adjudicadas · ${org.desiertas || 0} desiertas<br>
        Oferentes promedio: ${org.oferentes_promedio == null ? "—" : nf1.format(org.oferentes_promedio)}</p>
        <p class="small">Proveedores que más le ganan: ${org.top_proveedores.map((p) => `${esc(p.nombre)} (${p.ganadas})`).join(", ") || "—"}</p>` : ""}</div>
    </div>`;
}

// ---------- Búsqueda ----------
let paginaActual = 1;
async function buscar(pagina = 1) {
  paginaActual = pagina;
  const fd = Object.fromEntries(new FormData($("#f-buscar")));
  const r = await api("/api/licitaciones?" + qs({ ...fd, pagina, por_pagina: 25 }));
  $("#b-total").textContent = `${nf.format(r.total)} licitaciones`;
  const t = $("#b-tabla");
  t.innerHTML = r.resultados.length ? `<thead><tr><th>Licitación</th><th>Estado</th><th>Organismo</th><th class="num">Monto est.</th><th class="num">Cierre</th></tr></thead><tbody>` +
    r.resultados.map((l) => `<tr class="click" data-cod="${esc(l.codigo)}">
      <td><b>${esc(l.nombre)}</b><div class="small">${esc(l.codigo)}${l.tipo ? " · " + esc(l.tipo) : ""}${l.rubros.length ? " · " + l.rubros.map(esc).join(" · ") : ""}</div></td>
      <td>${pill(l.estado_codigo, l.estado)}</td>
      <td>${esc(l.organismo || "")}<div class="small">${esc(l.region || "")}</div></td>
      <td class="num">${clp(l.monto_estimado)}</td><td class="num">${fecha(l.fecha_cierre)}</td></tr>`).join("") + "</tbody>"
    : `<tr><td class="empty">Sin resultados</td></tr>`;
  $$("tr.click", t).forEach((tr) => tr.addEventListener("click", () => abrirLicitacion(tr.dataset.cod)));
  const paginas = Math.ceil(r.total / r.por_pagina);
  $("#b-pag").innerHTML = paginas > 1 ? `<button class="ghost" ${pagina <= 1 ? "disabled" : ""} data-p="${pagina - 1}">Anterior</button>
    <span class="small">Página ${pagina} de ${paginas}</span>
    <button class="ghost" ${pagina >= paginas ? "disabled" : ""} data-p="${pagina + 1}">Siguiente</button>` : "";
  $$("#b-pag button").forEach((b) => b.addEventListener("click", () => buscar(+b.dataset.p)));
}
$("#f-buscar").addEventListener("submit", (e) => { e.preventDefault(); buscar(1); });

// ---------- Datos y sincronización ----------
let pollSync = null;
async function cargarEstado() {
  const e = await api("/api/estado");
  $("#d-estado").innerHTML = [
    ["Licitaciones", e.total], ["Abiertas", e.activas], ["Adjudicadas", e.adjudicadas], ["Sin detalle", e.sin_detalle],
  ].map(([k, v]) => `<div class="stat"><div class="v">${nf.format(v || 0)}</div><div class="k">${k}</div></div>`).join("") +
    `<div class="stat"><div class="v" style="font-size:14px">${fecha(e.desde)} – ${fecha(e.hasta)}</div><div class="k">Período</div></div>`;
  $("#d-log").textContent = e.sync.mensajes.join("\n") || (e.ticket_configurado ? "Listo para sincronizar." : "Falta configurar MP_TICKET.");
  $$("[data-sync]").forEach((b) => (b.disabled = e.sync.corriendo || !e.ticket_configurado || e.demo));
  if (e.sync.corriendo && !pollSync) pollSync = setInterval(cargarEstado, 2000);
  if (!e.sync.corriendo && pollSync) { clearInterval(pollSync); pollSync = null; }
  return e;
}
$$("[data-sync]").forEach((b) => b.addEventListener("click", async () => {
  try {
    await api("/api/sync", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo: b.dataset.sync, dias: +$("#d-dias").value || 30, maximo: +$("#d-max").value || null }) });
    cargarEstado();
  } catch (e) { $("#d-log").textContent = e.message; }
}));

// ---------- Inicio ----------
(async function init() {
  const [f, e] = await Promise.all([api("/api/filtros"), cargarEstado()]);
  const opts = (arr) => arr.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
  $("#op-region").insertAdjacentHTML("beforeend", opts(f.regiones));
  $("#f-buscar [name=region]").insertAdjacentHTML("beforeend", opts(f.regiones));
  $("#f-buscar [name=rubro]").insertAdjacentHTML("beforeend", opts(f.rubros));
  $("#f-buscar [name=tipo]").insertAdjacentHTML("beforeend", opts(f.tipos));
  $("#f-buscar [name=estado]").insertAdjacentHTML("beforeend", f.estados.map((s) => `<option value="${s.codigo}">${esc(s.nombre)}</option>`).join(""));
  const b = $("#banner");
  if (e.demo) { b.textContent = "Estás viendo datos de demostración (ficticios). Para usar datos reales, configura tu ticket y sincroniza desde la pestaña Datos."; b.hidden = false; }
  else if (!e.total) { b.textContent = "La base está vacía. Ve a la pestaña Datos para descargar licitaciones."; b.hidden = false; }
  cargarOportunidades();
})();
