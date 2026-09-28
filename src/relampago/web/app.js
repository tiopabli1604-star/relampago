"use strict";
const $ = (s) => document.querySelector(s);
const q = $("#q"), lista = $("#lista"), detalle = $("#detalle"), ayuda = $("#ayuda");
let resultados = [], sel = 0, cidActual = 0, armado = null, avisoT = null, listo = false;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const esEmoji = (s) => /\p{Extended_Pictographic}|\p{Regional_Indicator}/u.test(s) && !/^[A-Za-z0-9]/.test(s);

/* Markdown mínimo para las respuestas de la IA: bloques ``` , `código` y **negrita** */
function markdown(t) {
  const partes = String(t).split(/```/);
  return partes.map((p, i) => {
    if (i % 2) {
      const cuerpo = p.replace(/^[\w+-]*\n/, "");
      return `<pre><code>${esc(cuerpo.replace(/\n$/, ""))}</code></pre>`;
    }
    return esc(p).replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  }).join("");
}

function api() { return window.pywebview && window.pywebview.api; }

function ajustarAlto() {
  requestAnimationFrame(() => {
    const h = $("#caja").getBoundingClientRect().height;
    api() && api().alto(Math.ceil(h));
  });
}

function pintar() {
  const hayTexto = q.value.trim().length > 0;
  ayuda.hidden = hayTexto || resultados.length > 0;
  lista.innerHTML = resultados.map((r, i) => {
    const icono = r.icono || "•";
    const emoji = esEmoji(icono);
    const color = r.color != null ? `style="--c: var(--c${r.color})"` : "";
    const aviso = armado === r.id && r.confirmar;
    return `<li role="option" data-i="${i}" class="${i === sel ? "sel" : ""}" aria-selected="${i === sel}">
      <div class="av ${emoji ? "emoji" : ""}" ${emoji ? "" : color}>${esc(icono)}</div>
      <div><div class="tit">${esc(r.titulo)}</div>
      <div class="sub ${aviso ? "aviso" : ""}">${esc(aviso ? r.confirmar : r.subtitulo)}</div></div>
      <div class="acc">${r.accion ? esc(r.accion) + " ↵" : ""}</div></li>`;
  }).join("");
  const r = resultados[sel];
  if (r && r.detalle) {
    detalle.hidden = false;
    const abajo = detalle.scrollTop + detalle.clientHeight >= detalle.scrollHeight - 8;
    detalle.innerHTML = markdown(r.detalle);
    if (abajo) detalle.scrollTop = detalle.scrollHeight;  // seguir el streaming
  } else {
    detalle.hidden = true;
  }
  $("#accion").textContent = r && r.accion ? r.accion.toLowerCase() : "—";
  $("#pie-alt").hidden = !(r && r.alt);
  $("#alt").textContent = r && r.alt ? r.alt.toLowerCase() : "";
  lista.querySelector("li.sel")?.scrollIntoView({ block: "nearest" });
  ajustarAlto();
}

async function buscar() {
  if (!api()) return;
  armado = null;
  const texto = q.value;
  const r = await api().buscar(texto);
  if (texto !== q.value) return;         // llegó tarde
  cidActual = r.cid;
  resultados = r.resultados;
  sel = 0;
  pintar();
}

function avisar(texto) {
  const a = $("#aviso");
  a.textContent = texto || "";
  clearTimeout(avisoT);
  avisoT = setTimeout(() => (a.textContent = ""), 2500);
}

async function ejecutar(alternativa) {
  const r = resultados[sel];
  if (!r) return;
  if (r.confirmar && !alternativa && armado !== r.id) {
    armado = r.id;
    pintar();
    return;
  }
  armado = null;
  const res = await api().ejecutar(r.id, !!alternativa);
  if (res && res.aviso) avisar(res.aviso);
  if (res && res.limpiar) { q.value = ""; }
  if (res && typeof res.texto === "string") { q.value = res.texto; }
  if (res && (res.limpiar || res.refrescar || typeof res.texto === "string")) buscar();
  else if (res && res.ocultar === false) pintar();
}

q.addEventListener("input", buscar);
q.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || (e.key === "n" && e.ctrlKey)) {
    e.preventDefault(); if (resultados.length) { sel = (sel + 1) % resultados.length; armado = null; pintar(); }
  } else if (e.key === "ArrowUp" || (e.key === "p" && e.ctrlKey)) {
    e.preventDefault(); if (resultados.length) { sel = (sel - 1 + resultados.length) % resultados.length; armado = null; pintar(); }
  } else if (e.key === "Enter") {
    e.preventDefault(); ejecutar(e.ctrlKey);
  } else if (e.key === "Escape") {
    e.preventDefault();
    if (armado) { armado = null; pintar(); }
    else if (q.value) { q.value = ""; buscar(); }
    else api().ocultar();
  } else if (e.key === "Tab") {
    e.preventDefault();
    const r = resultados[sel];
    if (r && r.completar) { q.value = r.completar; buscar(); }
    else if (r) { q.value = r.titulo; buscar(); }
  } else if (e.key === "PageDown" && !detalle.hidden) {
    e.preventDefault(); detalle.scrollTop += detalle.clientHeight - 40;
  } else if (e.key === "PageUp" && !detalle.hidden) {
    e.preventDefault(); detalle.scrollTop -= detalle.clientHeight - 40;
  }
});
lista.addEventListener("mousemove", (e) => {
  const li = e.target.closest("li");
  if (li && +li.dataset.i !== sel) { sel = +li.dataset.i; armado = null; pintar(); }
});
lista.addEventListener("click", (e) => { if (e.target.closest("li")) ejecutar(e.ctrlKey); });
window.addEventListener("blur", () => { if (listo) api() && api().ocultar(true); });

window.relampago = {
  /* pinta un estado fijo (capturas del modo navegador) */
  fijar(texto, res) {
    q.value = texto; resultados = res; sel = 0; cidActual = -1; pintar();
  },
  actualizar(cid, res) {
    if (cid !== cidActual) return;
    const id = resultados[sel] && resultados[sel].titulo;
    resultados = res;
    const i = resultados.findIndex((r) => r.titulo === id);
    sel = i >= 0 ? i : Math.min(sel, Math.max(0, resultados.length - 1));
    pintar();
  },
  mostrar() {
    listo = false;
    q.focus();
    q.select();
    buscar();
    setTimeout(() => { listo = true; q.focus(); }, 250);   // evita que el blur del arranque la cierre
  },
};

window.addEventListener("pywebviewready", async () => {
  const info = await api().inicio();
  $("#atajo").textContent = info.atajo.split("+").map((p) => p === "space" ? "Espacio" : p[0].toUpperCase() + p.slice(1)).join("+");
  ayuda.innerHTML = `<h2>Prueba a escribir</h2><div class="ejemplos">${info.ejemplos.map(([n, e]) =>
    `<button data-e="${esc(e.split(" · ")[0])}"><b>${esc(n)}</b><span>${esc(e)}</span></button>`).join("")}</div>` +
    (info.error_atajo ? `<div class="error-atajo">⚠ ${esc(info.error_atajo)}</div>` : "");
  ayuda.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { q.value = b.dataset.e; q.focus(); buscar(); }));
  pintar();
});
