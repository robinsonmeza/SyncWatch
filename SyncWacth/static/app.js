/* SyncWatch — lógica del dashboard (sin frameworks) */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (url, opts) => {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
};
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toFixed(d));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const COLOR = {
  cpu: "#7dd3fc", ram: "#c4b5fd", disk: "#5eead4", gpu: "#f9a8d4", temp: "#fdba74",
  ok: "#34d399", warn: "#fbbf24", crit: "#f87171", grid: "rgba(255,255,255,.06)", tick: "#6b7699",
};
const NIVEL_TXT = { normal: "Normal", advertencia: "Advertencia", critico: "Crítico" };

let vista = "monitor";
let umbrales = {};
let sistema = {};

/* ------------------------------------------------------------------ pestañas */
$$("nav.tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    $$("nav.tabs button").forEach((x) => x.classList.toggle("activa", x === b));
    $$(".vista").forEach((v) => v.classList.toggle("activa", v.id === `vista-${b.dataset.vista}`));
    vista = b.dataset.vista;
    if (vista === "monitor") cargarProcesos();
    if (vista === "lab") refrescarSim();
    if (vista === "registro") renderEventos();
    Object.values(graficos).forEach((g) => g && g.resize());
  })
);

/* ------------------------------------------------------------------ gráficos */
Chart.defaults.color = COLOR.tick;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11;

function lineas(canvas, series, { max = 100, sufijo = "%" } = {}) {
  return new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: series.map((s) => ({
        label: s.label, data: [], borderColor: s.color, borderWidth: 2, pointRadius: 0, tension: 0.35,
        fill: s.fill ? "origin" : false,
        backgroundColor: (ctx) => {
          const { chartArea, ctx: c } = ctx.chart;
          if (!chartArea) return "transparent";
          const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          g.addColorStop(0, s.color + "40"); g.addColorStop(1, s.color + "00");
          return g;
        },
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15,20,40,.92)", borderColor: "rgba(255,255,255,.15)", borderWidth: 1,
          padding: 10, cornerRadius: 10,
          callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y, 1)} ${sufijo}` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
        y: { min: 0, max, grid: { color: COLOR.grid }, border: { display: false }, ticks: { maxTicksLimit: 5, callback: (v) => v + (sufijo === "%" ? "%" : "") } },
      },
    },
  });
}

const graficos = {
  real: lineas($("#graf-real"), [{ label: "CPU", color: COLOR.cpu, fill: true }, { label: "RAM", color: COLOR.ram }]),
  sim: lineas($("#graf-sim"), [
    { label: "CPU sim", color: COLOR.cpu }, { label: "GPU sim", color: COLOR.gpu },
    { label: "RAM sim", color: COLOR.ram }, { label: "Temp sim", color: COLOR.temp },
  ], { max: 110, sufijo: "" }),
  cmp: new Chart($("#graf-cmp"), {
    type: "bar",
    data: { labels: [], datasets: [
      { label: "Perdidos", data: [], backgroundColor: COLOR.crit, borderRadius: 6, maxBarThickness: 18 },
      { label: "Duplicados", data: [], backgroundColor: COLOR.warn, borderRadius: 6, maxBarThickness: 18 },
      { label: "Lecturas vacías", data: [], backgroundColor: COLOR.ram, borderRadius: 6, maxBarThickness: 18 },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } } },
      scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: COLOR.grid }, ticks: { precision: 0 } } },
    },
  }),
};

/* ------------------------------------------------------------------ utilidades UI */
function nivelDe(metrica, valor) {
  const u = umbrales[metrica];
  if (!u || valor === null || valor === undefined) return "normal";
  if (valor >= u.critico) return "critico";
  if (valor >= u.advertencia) return "advertencia";
  return "normal";
}
const colorNivel = (n, base) => (n === "critico" ? COLOR.crit : n === "advertencia" ? COLOR.warn : base);

function anillo(card, pct, color) {
  const arco = $(".arco", card);
  if (!arco) return;
  const L = 2 * Math.PI * 26;
  arco.style.strokeDasharray = L;
  arco.style.strokeDashoffset = L * (1 - Math.min(100, Math.max(0, pct || 0)) / 100);
  arco.style.stroke = color;
}

function kpi(id, valor, sub, metrica, base) {
  const card = $(id);
  const n = nivelDe(metrica, valor);
  $(".valor", card).innerHTML = `${fmt(valor, 0)}<small>%</small>`;
  $(".sub", card).textContent = sub;
  anillo(card, valor, colorNivel(n, base));
  card.style.borderColor = n === "normal" ? "" : n === "critico" ? "rgba(248,113,113,.55)" : "rgba(251,191,36,.45)";
}

function toast(nivel, texto) {
  const t = document.createElement("div");
  t.className = `glass toast ${nivel}`;
  t.innerHTML = `<b>${nivel === "critico" ? "ALERTA CRÍTICA" : "ADVERTENCIA"}</b>${esc(texto)}`;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 6000);
  while ($("#toasts").children.length > 3) $("#toasts").firstChild.remove();
}

/* ------------------------------------------------------------------ MONITOR */
async function cargarSistema() {
  sistema = await api("/api/sistema");
  $("#chip-host").innerHTML = `<span class="punto"></span><span>${esc(sistema.equipo)} · ${esc(sistema.so)}</span>`;
  renderLimitaciones();
}

async function cargarMetricas() {
  let d;
  try { d = await api("/api/metricas"); } catch { $("#chip-host .punto").style.background = COLOR.crit; return; }
  const m = d.actual;
  kpi("#kpi-cpu", m.cpu, `${sistema.nucleos_fisicos || "?"} núcleos físicos · ${sistema.nucleos_logicos || "?"} lógicos`, "cpu", COLOR.cpu);
  kpi("#kpi-ram", m.ram, `${fmt(m.ram_usada_gb, 1)} de ${fmt(m.ram_total_gb, 1)} GB · swap ${fmt(m.swap, 0)}%`, "ram", COLOR.ram);
  kpi("#kpi-disco", m.disco, `${fmt(m.disco_info.usado_gb, 0)} de ${fmt(m.disco_info.total_gb, 0)} GB · ${m.disco_info.unidad}`, "disco", COLOR.disk);

  const h = d.historial;
  const g = graficos.real;
  g.data.labels = h.map((x) => new Date(x.t * 1000).toLocaleTimeString("es", { hour12: false }));
  g.data.datasets[0].data = h.map((x) => x.cpu);
  g.data.datasets[1].data = h.map((x) => x.ram);
  g.update("none");

  $("#nucleos").innerHTML = (m.cpu_nucleos || []).map((v, i) => {
    const c = colorNivel(nivelDe("cpu", v), COLOR.cpu);
    return `<div class="nucleo" title="Núcleo ${i}: ${fmt(v, 0)}%"><div class="col"><div style="height:${Math.max(2, v)}%;background:linear-gradient(to top, ${c}55, ${c})"></div></div>${i}</div>`;
  }).join("");

  renderAlertas(d.alertas);
  renderRegistro(d.registro);
}

function renderAlertas(lista) {
  const chip = $("#chip-alertas");
  const crit = lista.filter((a) => a.nivel === "critico").length;
  chip.className = `chip alerta ${crit ? "critico" : lista.length ? "advertencia" : ""}`;
  chip.textContent = lista.length ? `${lista.length} alerta${lista.length > 1 ? "s" : ""} activa${lista.length > 1 ? "s" : ""}` : "Sin alertas";
  $("#lista-alertas").innerHTML = lista.length
    ? lista.sort((a, b) => (a.nivel === "critico" ? -1 : 1)).map((a) => `
        <div class="alerta-item"><span class="estado-pill n-${a.nivel}">${NIVEL_TXT[a.nivel]}</span>
        <span>${esc(a.nombre)} <span class="tag ${a.origen === "real" ? "real" : "sim"}">${a.origen === "real" ? "REAL" : "SIM"}</span></span>
        <b>${fmt(a.valor, 1)}</b></div>`).join("")
    : `<div class="vacio"><span class="ok">✓</span>Todo dentro de los umbrales</div>`;
}

let ordenProc = "cpu";
$$("#seg-orden button").forEach((b) => b.addEventListener("click", () => {
  ordenProc = b.dataset.orden;
  $$("#seg-orden button").forEach((x) => x.classList.toggle("activa", x === b));
  cargarProcesos();
}));

async function cargarProcesos() {
  const d = await api(`/api/procesos?orden=${ordenProc}&limite=8`);
  $("#kpi-proc .valor").textContent = d.total;
  $("#kpi-proc .sub").textContent = d.restringidos ? `${d.restringidos} con datos restringidos` : "Acceso completo";
  const max = Math.max(1, ...d.procesos.map((p) => p[ordenProc]));
  $("#tabla-procesos").innerHTML = d.procesos.map((p) => `
    <tr><td style="color:var(--faint)">${p.pid}</td>
    <td class="nombre" title="${esc(p.nombre)}">${esc(p.nombre)}
      <div class="barrita"><div style="width:${(100 * p[ordenProc]) / max}%;background:${ordenProc === "cpu" ? COLOR.cpu : COLOR.ram}"></div></div></td>
    <td class="num">${fmt(p.cpu, 1)}</td><td class="num">${fmt(p.ram, 1)}</td>
    <td class="nombre" style="color:var(--faint);max-width:140px">${esc(p.usuario)}</td></tr>`).join("");
  $("#nota-procesos").textContent = d.restringidos
    ? `${d.restringidos} de ${d.total} procesos no permiten leer usuario o memoria sin permisos de administrador (AccessDenied). El % de CPU por proceso se normaliza al total de núcleos.`
    : "Todos los procesos fueron legibles. El % de CPU por proceso se normaliza al total de núcleos.";
}

/* ------------------------------------------------------------------ LABORATORIO */
const CAMPOS = [
  { k: "capacidad", t: "Capacidad del búfer", min: 1, max: 20, step: 1 },
  { k: "productores", t: "Productores", min: 1, max: 8, step: 1 },
  { k: "consumidores", t: "Consumidores", min: 1, max: 8, step: 1 },
  { k: "items_por_productor", t: "Ítems por productor", min: 1, max: 200, step: 1 },
  { k: "t_produccion", t: "Tiempo de producción (s/ítem)", min: 0.02, max: 1.5, step: 0.01 },
  { k: "t_consumo", t: "Tiempo de consumo (s/ítem)", min: 0.02, max: 1.5, step: 0.01 },
];
let catalogo = [];
let simActiva = false;
let ultimaSerieLen = -1;

$("#campos-cfg").innerHTML = CAMPOS.map((c) => `
  <label class="campo"><span class="cab">${c.t}<b id="v-${c.k}"></b></span>
  <input type="range" id="cfg-${c.k}" min="${c.min}" max="${c.max}" step="${c.step}"></label>`).join("");
CAMPOS.forEach((c) => $(`#cfg-${c.k}`).addEventListener("input", (e) => ($(`#v-${c.k}`).textContent = e.target.value)));

function aplicarEscenario(clave) {
  const e = catalogo.find((x) => x.clave === clave);
  if (!e) return;
  $("#esc-desc").textContent = e.descripcion;
  $("#esc-observar").innerHTML = `<b>Qué observar:</b> ${esc(e.observar)}`;
  CAMPOS.forEach((c) => { $(`#cfg-${c.k}`).value = e.config[c.k]; $(`#v-${c.k}`).textContent = e.config[c.k]; });
  $("#cfg-sincronizado").checked = e.config.sincronizado;
  $("#cfg-semilla").value = e.config.semilla;
}

async function cargarEscenarios() {
  const d = await api("/api/escenarios");
  catalogo = d.escenarios;
  $("#sel-escenario").innerHTML = catalogo.map((e, i) => `<option value="${e.clave}">${i + 1}. ${esc(e.nombre)}</option>`).join("");
  aplicarEscenario(catalogo[0].clave);
}
$("#sel-escenario").addEventListener("change", (e) => aplicarEscenario(e.target.value));

$("#btn-iniciar").addEventListener("click", async () => {
  const config = { sincronizado: $("#cfg-sincronizado").checked, semilla: Number($("#cfg-semilla").value) };
  CAMPOS.forEach((c) => (config[c.k] = Number($(`#cfg-${c.k}`).value)));
  ultimaSerieLen = -1;
  await post("/api/sim/iniciar", { escenario: $("#sel-escenario").value, config });
  refrescarSim();
});
$("#btn-detener").addEventListener("click", () => post("/api/sim/detener").then(refrescarSim));

const ESTADO_HILO = {
  listo: ["listo", ""], produciendo: ["produciendo", "trabajando"], insertando: ["insertando", "trabajando"],
  esperando: ["esperando", ""], consumiendo: ["consumiendo", "trabajando"],
  bloqueado_lleno: ["bloqueado · lleno", "bloqueado"], bloqueado_vacio: ["bloqueado · vacío", "bloqueado"],
  terminado: ["terminado", "terminado"],
};
const hiloHTML = (h) => {
  const [txt, cls] = ESTADO_HILO[h.estado] || [h.estado, ""];
  return `<div class="hilo ${cls}" title="${h.hechos} ítems · ${h.bloqueos} bloqueos · ${h.t_bloqueado}s bloqueado"><i class="led"></i><b>${h.nombre}</b><span>${txt}</span></div>`;
};

async function refrescarSim() {
  let s;
  try { s = await api("/api/sim/estado"); } catch { return; }
  if (!s.existe) return;
  simActiva = s.activa;
  $("#btn-detener").disabled = !s.activa;

  const sync = s.buffer.sincronizado;
  const modo = $("#lab-modo");
  modo.className = `modo ${sync ? "con" : "sin"}`;
  modo.textContent = sync ? "CON SINCRONIZACIÓN" : "SIN SINCRONIZACIÓN";
  $("#lab-estado").textContent = s.activa ? "● En ejecución" : `Terminada · ${s.motivo_fin || ""}`;
  $("#lab-tiempo").textContent = `${fmt(s.transcurrido, 1)} s`;
  $("#lab-explicacion").textContent = s.explicacion;

  $("#lab-productores").innerHTML = s.hilos.filter((h) => h.tipo === "productor").map(hiloHTML).join("");
  $("#lab-consumidores").innerHTML = s.hilos.filter((h) => h.tipo === "consumidor").map(hiloHTML).join("");

  const b = s.buffer;
  $("#lab-buffer").innerHTML = b.casillas.map((it, i) => {
    const marca = i === b.entrada && i === b.salida ? '<span class="pos in">in·out</span>'
      : i === b.entrada ? '<span class="pos in">in</span>' : i === b.salida ? '<span class="pos out">out</span>' : "";
    return `<div class="casilla ${it ? "llena" : ""}" title="Casilla ${i}${it ? ": " + esc(it) : " (vacía)"}">${it ? esc(it) : i}${marca}</div>`;
  }).join("");
  $("#lab-buffer").className = `buffer ${b.ocupadas === b.capacidad ? "estado-lleno" : b.ocupadas === 0 ? "estado-vacio" : ""}`;
  $("#buf-ocupacion").textContent = `${b.ocupadas} / ${b.capacidad} ocupadas${b.ocupadas === b.capacidad ? " · LLENO" : b.ocupadas === 0 ? " · VACÍO" : ""}`;
  const cuentaMal = b.cuenta !== b.ocupadas;
  $("#buf-cuenta").innerHTML = `cuenta interna: <b style="color:${cuentaMal ? COLOR.crit : "inherit"}">${b.cuenta}</b>${cuentaMal ? " ≠ real" : ""}`;
  $("#sem-esp").textContent = b.espacios_libres ?? "—";
  $("#sem-items").textContent = b.items_disponibles ?? "—";
  $("#sem-mutex").textContent = b.mutex === "ocupado" ? `ocupado (${b.mutex_duenio})` : b.mutex;
  $("#sem-mutex").style.color = b.mutex === "sin mutex" ? COLOR.crit : "";

  const a = s.auditoria;
  $("#c-prod").textContent = a.producidos;
  $("#c-cons").textContent = a.consumidos;
  $("#c-buf").textContent = a.en_buffer;
  $("#c-bloq").textContent = s.bloqueos_total;
  const tb = (tipo) => s.hilos.filter((h) => h.tipo === tipo).reduce((acc, h) => acc + h.t_bloqueado, 0);
  $("#t-bloqueado").innerHTML = `Tiempo total bloqueado: productores <b>${fmt(tb("productor"), 1)} s</b> (búfer lleno) · consumidores <b>${fmt(tb("consumidor"), 1)} s</b> (búfer vacío). Pasa el cursor sobre un hilo para ver su detalle.`;
  const cons = $("#conservacion");
  cons.className = `conservacion ${a.conservacion_ok ? "ok" : "falla"}`;
  cons.innerHTML = a.conservacion_ok
    ? `<span class="ico" style="color:var(--ok)">✓</span><span>Conservación correcta: <code>${a.producidos} = ${a.consumidos_unicos} + ${a.en_buffer}</code></span>`
    : `<span class="ico" style="color:var(--crit)">✗</span><span>Conservación rota: <code>${a.producidos} ≠ ${a.consumidos_unicos} + ${a.en_buffer}</code> · perdidos <b>${a.perdidos}</b> · duplicados <b>${a.duplicados}</b> · vacías <b>${a.lecturas_vacias}</b></span>`;

  const c = s.carga;
  [["#s-cpu", c.cpu_sim, "cpu_sim", "%"], ["#s-gpu", c.gpu_sim, "gpu_sim", "%"], ["#s-ram", c.ram_sim, "ram_sim", "%"], ["#s-temp", c.temp_sim, "temp_sim", "°"]]
    .forEach(([sel, v, k, u]) => { const el = $(sel); el.textContent = fmt(v, 0) + u; el.style.color = colorNivel(nivelDe(k, v), ""); });
  if (s.serie.length !== ultimaSerieLen || s.activa) {
    ultimaSerieLen = s.serie.length;
    const g = graficos.sim;
    g.data.labels = s.serie.map((x) => x.t.toFixed(1) + " s");
    ["cpu_sim", "gpu_sim", "ram_sim", "temp_sim"].forEach((k, i) => (g.data.datasets[i].data = s.serie.map((x) => x[k])));
    g.update("none");
  }
}

/* ------------------------------------------------------------------ COMPARACIÓN */
const FILAS_CMP = [
  ["producidos", "Ítems producidos"], ["consumidos", "Ítems consumidos"], ["en_buffer", "Quedaron en el búfer"],
  ["perdidos", "Perdidos (sobrescritos)", true], ["duplicados", "Consumidos dos veces", true],
  ["lecturas_vacias", "Lecturas de casilla vacía", true], ["desbordes", "Cuenta fuera de rango", true],
  ["cuenta_final", "Cuenta interna vs. real", true], ["bloqueos", "Esperas / bloqueos"], ["tiempo", "Tiempo (s)"],
];
function renderVersus(sel, r, sync) {
  const card = $(sel);
  const ok = r.conservacion_ok;
  card.className = `glass card versus ${ok ? "bien" : "mal"}`;
  $(".ico", card).textContent = ok ? "✓" : "✗";
  $(".veredicto small", card).textContent = ok ? "Correcto: producidos = consumidos + en búfer"
    : "Condición de carrera detectada: la regla de conservación no se cumple";
  $("tbody", card).innerHTML = FILAS_CMP.map(([k, t, anom]) => {
    let v = r[k], malo = false;
    if (k === "cuenta_final") { v = `${r.cuenta_buffer} vs ${r.en_buffer}`; malo = r.cuenta_buffer !== r.en_buffer; }
    else if (anom) malo = v > 0;
    return `<tr><td>${t}</td><td class="num ${anom ? (malo ? "malo" : "bueno") : ""}">${v}</td></tr>`;
  }).join("");
}

$("#btn-comparar").addEventListener("click", async () => {
  const cfg = {
    capacidad: +$("#cmp-capacidad").value, productores: +$("#cmp-productores").value,
    consumidores: +$("#cmp-consumidores").value, items_por_productor: +$("#cmp-items").value,
    semilla: +$("#cmp-semilla").value, t_produccion: 0.02, t_consumo: 0.02,
  };
  const btn = $("#btn-comparar");
  btn.disabled = true; btn.textContent = "Ejecutando…";
  try { await post("/api/comparar", { config: cfg }); } catch {}
  const espera = setInterval(async () => {
    const d = await api("/api/comparar");
    if (!d.ejecutando) {
      clearInterval(espera);
      btn.disabled = false; btn.textContent = "Ejecutar comparación";
      renderComparacion(d);
    }
  }, 400);
});

function renderComparacion(d) {
  if (d.resultado) {
    renderVersus("#cmp-sin", d.resultado.sin, false);
    renderVersus("#cmp-con", d.resultado.con, true);
    const s = d.resultado.sin;
    $("#cmp-ids").innerHTML =
      (s.ejemplo_perdidos.length ? `Ejemplos de ítems perdidos: ${s.ejemplo_perdidos.map((x) => `<code>${x}</code>`).join(" ")}<br>` : "") +
      (s.ejemplo_duplicados.length ? `Ejemplos de ítems duplicados: ${s.ejemplo_duplicados.map((x) => `<code>${x}</code>`).join(" ")}` : "");
  }
  const h = d.historial || [];
  const g = graficos.cmp;
  g.data.labels = h.map((x) => `#${x.id}`);
  g.data.datasets[0].data = h.map((x) => x.sin.perdidos);
  g.data.datasets[1].data = h.map((x) => x.sin.duplicados);
  g.data.datasets[2].data = h.map((x) => x.sin.lecturas_vacias);
  g.update();
  $("#cmp-historial").innerHTML = h.slice().reverse().map((x) => `
    <tr><td>${x.id}</td><td style="color:var(--faint)">${x.hora}</td><td class="num">${x.sin.perdidos}</td>
    <td class="num">${x.sin.duplicados}</td><td class="num">${x.sin.lecturas_vacias}</td>
    <td><span class="estado-pill ${x.con.conservacion_ok ? "n-normal" : "n-critico"}">${x.con.conservacion_ok ? "OK" : "FALLA"}</span></td></tr>`).join("")
    || `<tr><td colspan="6" class="vacio">Aún no hay ejecuciones</td></tr>`;
}

/* ------------------------------------------------------------------ REGISTRO */
let eventos = [];
let ultimoEvento = 0;
let filtroNivel = "";
let primeraCarga = true;

async function cargarEventos() {
  let nuevos;
  try { nuevos = await api(`/api/eventos?desde=${ultimoEvento}`); } catch { return; }
  if (!nuevos.length) return;
  ultimoEvento = nuevos[nuevos.length - 1].id;
  eventos = eventos.concat(nuevos).slice(-400);
  if (!primeraCarga) nuevos.filter((e) => e.nivel === "critico" && (e.origen === "alerta" || e.origen === "simulacion")).slice(-2).forEach((e) => toast("critico", e.mensaje));
  primeraCarga = false;
  if (vista === "registro") renderEventos();
}

function renderEventos() {
  const org = $("#sel-origen").value;
  const lista = eventos.filter((e) => (!filtroNivel || e.nivel === filtroNivel) && (!org || e.origen === org)).slice(-200).reverse();
  $("#eventos").innerHTML = lista.map((e) => `
    <div class="evento ${e.nivel}"><i class="niv"></i><time>${e.hora}</time><span class="org">${e.origen}</span><span>${esc(e.mensaje)}</span></div>`).join("")
    || `<div class="vacio">No hay eventos con este filtro</div>`;
}
$$("#seg-nivel button").forEach((b) => b.addEventListener("click", () => {
  filtroNivel = b.dataset.nivel;
  $$("#seg-nivel button").forEach((x) => x.classList.toggle("activa", x === b));
  renderEventos();
}));
$("#sel-origen").addEventListener("change", renderEventos);

function renderRegistro(r) {
  if (document.activeElement !== $("#reg-activo")) $("#reg-activo").checked = r.activo;
  const base = r.activo ? `Guardando cada ${r.intervalo} s en ${r.archivo} · ${r.filas} filas` : r.archivo ? `Detenido · último archivo ${r.archivo} (${r.filas} filas)` : "Inactivo";
  $("#reg-estado").innerHTML = `${esc(base)}<br>Carpeta: <span style="font-family:var(--mono);word-break:break-all">${esc(r.carpeta || "")}</span>`;
}
const enviarRegistro = () => post("/api/registro", { activo: $("#reg-activo").checked, intervalo: +$("#reg-intervalo").value }).then(renderRegistro);
$("#reg-activo").addEventListener("change", enviarRegistro);
$("#reg-intervalo").addEventListener("change", () => $("#reg-activo").checked && enviarRegistro());

async function cargarUmbrales() {
  umbrales = await api("/api/umbrales");
  $("#tabla-umbrales").innerHTML = Object.entries(umbrales).map(([k, u]) => `
    <tr><td>${esc(u.nombre)}</td>
    <td class="num"><input type="number" data-k="${k}" data-c="advertencia" value="${u.advertencia}"></td>
    <td class="num"><input type="number" data-k="${k}" data-c="critico" value="${u.critico}"></td></tr>`).join("");
}
$("#btn-umbrales").addEventListener("click", async () => {
  const datos = {};
  $$("#tabla-umbrales input").forEach((i) => ((datos[i.dataset.k] ??= {})[i.dataset.c] = Number(i.value)));
  const r = await fetch("/api/umbrales", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) }).then((x) => x.json());
  $("#umbrales-msg").innerHTML = r.ok ? "✓ Umbrales guardados." : `<span style="color:var(--crit)">Revisa: ${Object.keys(r.errores).join(", ")} (advertencia debe ser menor que crítico).</span>`;
  await cargarUmbrales();
});

function renderLimitaciones() {
  const s = sistema;
  const items = [
    `<b>Temperatura:</b> ${s.temperatura_disponible ? "disponible en este sistema." : "este sistema operativo no la expone a psutil (habitual en Windows); por eso en el laboratorio la temperatura es simulada."}`,
    `<b>Permisos:</b> ${s.administrador ? "se ejecuta como administrador; la lista de procesos es completa." : "se ejecuta sin privilegios de administrador; algunos procesos del sistema niegan el acceso (AccessDenied) y aparecen como restringidos."}`,
    `<b>CPU instantánea:</b> psutil calcula el % comparando con la lectura anterior; se usa un único hilo muestreador cada 1 s para no alterar el cálculo. Picos menores a 1 s pueden no verse.`,
    `<b>CPU por proceso:</b> puede superar 100 % en equipos multinúcleo; aquí se divide por ${s.nucleos_logicos || "N"} núcleos lógicos. El primer muestreo de un proceso nuevo vale 0 %.`,
    `<b>Disco:</b> se muestra solo la unidad principal; no incluye unidades externas o de red.`,
    `<b>GPU:</b> psutil no mide la GPU; en este proyecto la GPU solo aparece de forma simulada.`,
    `<b>Laboratorio:</b> usa hilos reales de Python, pero el trabajo y la carga del stress test son simulados (no se calienta el equipo). Por el GIL, los hilos de Python no ejecutan cálculo en paralelo real; para este experimento no importa porque lo que se estudia es el acceso concurrente al búfer.`,
  ];
  $("#limitaciones").innerHTML = items.map((x) => `<li>${x}</li>`).join("");
}

/* ------------------------------------------------------------------ arranque */
(async function iniciar() {
  await Promise.all([cargarSistema(), cargarUmbrales(), cargarEscenarios()]);
  cargarMetricas(); cargarProcesos(); cargarEventos(); refrescarSim();
  api("/api/comparar").then(renderComparacion);
  renderEventos();
  setInterval(cargarMetricas, 1000);
  setInterval(() => vista === "monitor" && cargarProcesos(), 3000);
  setInterval(cargarEventos, 1500);
  setInterval(() => (vista === "lab" || simActiva) && refrescarSim(), 350);
})();
