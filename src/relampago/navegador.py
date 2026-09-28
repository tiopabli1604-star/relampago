"""Modo navegador: la misma interfaz servida en http://127.0.0.1 con el motor real detrás.
Útil para probar/desarrollar la interfaz, hacer capturas o usarlo fuera de Windows.
Solo escucha en localhost y exige un token por sesión."""
from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WEB = Path(__file__).with_name("web")

PUENTE = """<script>
(() => {
  const token = "__TOKEN__";
  const llamar = (m, ...args) => fetch("/api/" + m, {method: "POST", headers: {"X-Token": token},
    body: JSON.stringify(args)}).then(r => r.json());
  window.pywebview = {api: new Proxy({}, {get: (_, m) => (...a) => llamar(m, ...a)})};
  // resultados tardíos (precios, IA…): peticiones cortas repetidas en vez de una conexión eterna
  // con ?q= (capturas automáticas) se deja de escuchar a los 4 s para que la página "termine"
  const fin = new URLSearchParams(location.search).has("q") ? Date.now() + 4000 : Infinity;
  (async function escuchar() {
    while (Date.now() < fin) {
      try {
        const r = await fetch("/eventos", {headers: {"X-Token": token}});
        for (const d of await r.json()) window.relampago.actualizar(d.cid, d.resultados);
      } catch (e) { await new Promise(ok => setTimeout(ok, 1000)); }
    }
  })();
  addEventListener("DOMContentLoaded", () => {
    window.dispatchEvent(new Event("pywebviewready"));
    const ini = window.__INICIAL__;   // ?q=… → resultados ya calculados en el servidor (capturas)
    if (ini) window.relampago.fijar(ini.q, ini.resultados);
    else setTimeout(() => window.relampago.mostrar(), 50);
  });
})();
</script>"""


class _AppFalsa:
    """Lo mínimo de Aplicacion que necesita la Api fuera de la ventana nativa."""

    def __init__(self, config, motor):
        self.config, self.motor, self.error_atajo = config, motor, None

    def ocultar(self):
        pass

    def ajustar_alto(self, px):
        pass


def servir(puerto: int = 8765):
    from .app import Api, Interno, cargar_config
    from .nucleo import Contexto, Motor, Uso
    from .plugins import TODOS
    from . import win

    config = cargar_config()
    ctx = Contexto(config, Uso(), copiar=win.escribir_portapapeles)
    motor = Motor(ctx, [*TODOS, Interno])
    app = _AppFalsa(config, motor)
    ctx.extras["app"] = app
    app.recargar = lambda: {"ocultar": False}
    app.salir = lambda: {"ocultar": False}
    api = Api(app)
    token = secrets.token_urlsafe(16)
    eventos: queue.Queue = queue.Queue()
    ultimos: dict[int, list] = {}   # último resultado empujado por cada búsqueda

    def al_actualizar(cid, r):
        ultimos[cid] = r
        eventos.put({"cid": cid, "resultados": r})

    motor.al_actualizar = al_actualizar
    motor.iniciar()

    def precalcular(texto: str, espera: float = 5.0) -> dict:
        """Busca y espera a los resultados tardíos (red) para devolver el estado final."""
        cid, res = motor.buscar(texto)
        fin = time.time() + espera
        while time.time() < fin:
            res = ultimos.get(cid, res)
            if not any(r["titulo"].startswith(("Consultando", "Cargando")) for r in res):
                break
            time.sleep(0.1)
        return {"q": texto, "resultados": res}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _enviar(self, codigo, cuerpo: bytes, tipo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta == "/eventos":
                if self.headers.get("X-Token") != token:
                    return self._enviar(403, b"[]", "application/json")
                lote = []
                try:
                    lote.append(eventos.get(timeout=1.5))   # espera corta: nunca deja la conexión colgada
                    while True:
                        lote.append(eventos.get_nowait())
                except queue.Empty:
                    pass
                return self._enviar(200, json.dumps(lote, ensure_ascii=False).encode(), "application/json")
            nombre = "index.html" if ruta == "/" else ruta.lstrip("/")
            f = (WEB / nombre).resolve()
            if WEB.resolve() not in f.parents or not f.is_file():
                return self._enviar(404, b"", "text/plain")
            datos = f.read_bytes()
            if f.name == "index.html":
                inicial = ""
                qs = parse_qs(urlparse(self.path).query)
                if "q" in qs:
                    inicial = f"<script>window.__INICIAL__ = {json.dumps(precalcular(qs['q'][0]), ensure_ascii=False)};</script>"
                datos = datos.replace(b"<script src=\"app.js\">", (inicial + PUENTE.replace("__TOKEN__", token)).encode()
                                      + b"<script src=\"app.js\">")
            tipo = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}.get(f.suffix, "text/plain")
            self._enviar(200, datos, tipo + "; charset=utf-8")

        def do_POST(self):
            if self.headers.get("X-Token") != token:
                return self._enviar(403, b"{}", "application/json")
            metodo = self.path.split("/api/")[-1]
            if metodo.startswith("_") or not hasattr(api, metodo):
                return self._enviar(404, b"{}", "application/json")
            args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"[]")
            res = getattr(api, metodo)(*args)
            self._enviar(200, json.dumps(res, ensure_ascii=False).encode(), "application/json")

    srv = ThreadingHTTPServer(("127.0.0.1", puerto), H)
    srv.daemon_threads = True
    print(f"relámpago (modo navegador) en http://127.0.0.1:{puerto}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
