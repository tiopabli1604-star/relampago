"""relámpago — lanzador universal para Windows. Alt+Espacio y escribe.

  relampago               arranca en segundo plano (Alt+Espacio para mostrar)
  relampago --inicio      arrancar automáticamente al encender el PC
  relampago --no-inicio   quitarlo del arranque
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__, win
from .nucleo import HOME, Contexto, Motor, Plugin, Resultado, Uso, normalizar, puntuar
from .plugins import TODOS

WEB = Path(__file__).with_name("web")
CONFIG = HOME / "config.json"
ANCHO = 760
POR_DEFECTO = {
    "atajo": "alt+space",
    "modelo_ia": None,
    "carpetas": [],
    "portapapeles": True,
    "snippets": {"correo": "tu@correo.com", "firma": "Un saludo,\nTu nombre"},
}


def cargar_config() -> dict:
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        propia = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        propia = {}
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(POR_DEFECTO, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**POR_DEFECTO, **propia}


# ---------------------------------------------------------------- comandos propios

class Interno(Plugin):
    nombre = "relampago"
    titulo = "relámpago"
    ejemplo = "ajustes · ayuda · salir"

    def buscar(self, consulta, empujar):
        q = normalizar(consulta)
        if len(q) < 3:
            return []
        app: Aplicacion = self.ctx.extras["app"]
        cmds = [
            ("Ajustes de relámpago", "ajustes configuracion config opciones relampago", "⚙",
             lambda: win.abrir(str(CONFIG)), "Abre config.json (atajo, snippets, carpetas, modelo de IA)"),
            ("Ayuda: todo lo que sabe hacer", "ayuda help que puedo relampago", "?",
             lambda: {"ocultar": False, "texto": ""}, "Ejemplos de cada función"),
            ("Recargar configuración y apps", "recargar reload actualizar relampago", "↻",
             app.recargar, "Tras editar config.json o instalar programas"),
            ("Arrancar relámpago con Windows", "inicio arranque autostart relampago", "🚀",
             lambda: {"ocultar": False, "aviso": instalar_inicio()}, "Crea un acceso en la carpeta Inicio"),
            ("Salir de relámpago", "salir cerrar quit exit relampago", "⏻", app.salir,
             "Cierra el lanzador (vuelve a abrirlo desde el menú Inicio)"),
        ]
        salida = []
        for titulo, claves, icono, accion, sub in cmds:
            s = max(puntuar(q, normalizar(titulo)), *(puntuar(q, k) for k in claves.split()))
            if s >= 60:
                salida.append(Resultado(titulo, sub, icono, 6, accion=accion, puntuacion=s,
                                        clave=f"int:{titulo}", accion_texto="Ejecutar"))
        return salida


# ---------------------------------------------------------------- arranque con Windows

def _acceso_inicio() -> Path:
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\relampago.lnk"


def instalar_inicio() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    lnk = _acceso_inicio()
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:RLP_LNK);"
          "$s.TargetPath = $env:RLP_EXE; $s.Arguments = '-m relampago';"
          "$s.WorkingDirectory = $env:USERPROFILE; $s.Description = 'relámpago'; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True,
                   env={**os.environ, "RLP_LNK": str(lnk), "RLP_EXE": str(pythonw)}, creationflags=0x08000000)
    return "relámpago arrancará con Windows"


def quitar_inicio() -> str:
    _acceso_inicio().unlink(missing_ok=True)
    return "relámpago ya no arranca con Windows"


# ---------------------------------------------------------------- aplicación

class Api:
    """Métodos que llama el JavaScript de la ventana (window.pywebview.api.*)."""

    def __init__(self, app: "Aplicacion"):
        self._app = app

    def buscar(self, texto: str):
        cid, res = self._app.motor.buscar(texto)
        return {"cid": cid, "resultados": res}

    def ejecutar(self, id_: int, alternativa: bool = False):
        try:
            r = self._app.motor.ejecutar(int(id_), bool(alternativa))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "aviso": f"Error: {e}"}
        if r.get("ocultar"):
            self._app.ocultar()
        return r

    def ocultar(self, por_foco: bool = False):
        # el aviso de "perdí el foco" puede llegar con retraso justo después de volver a mostrar
        # la ventana: si es así, se ignora
        if por_foco and time.time() - self._app.mostrado_en < 0.6:
            return
        self._app.ocultar()

    def alto(self, px: int):
        self._app.ajustar_alto(int(px))

    def inicio(self):
        return {"atajo": self._app.config["atajo"], "version": __version__,
                "ejemplos": [(p.titulo or p.nombre, p.ejemplo) for p in self._app.motor.plugins if p.ejemplo],
                "error_atajo": self._app.error_atajo}


class Aplicacion:
    def __init__(self):
        self.config = cargar_config()
        self.uso = Uso()
        self.visible = False
        self.mostrado_en = 0.0
        self.anterior = 0          # ventana que tenía el foco antes de abrir el lanzador
        self.hwnd = 0
        self.alto_actual = 0
        self.error_atajo: str | None = None
        self.ventana = None
        self.atajo: win.AtajoGlobal | None = None
        ctx = Contexto(self.config, self.uso, pegar=self.pegar, copiar=win.escribir_portapapeles,
                       notificar=lambda t, m: None, ocultar=self.ocultar, extras={"app": self})
        self.motor = Motor(ctx, [*TODOS, Interno])
        self.motor.al_actualizar = self._empujar

    # -------------------------------------------- ventana
    def _empujar(self, cid: int, resultados: list[dict]):
        if self.ventana is not None:
            self.ventana.evaluate_js(f"relampago.actualizar({cid}, {json.dumps(resultados, ensure_ascii=False)})")

    def _posicion(self) -> tuple[int, int]:
        import webview
        pant = webview.screens[0] if webview.screens else None
        if pant is None:
            return 300, 160
        return pant.x + (pant.width - ANCHO) // 2, pant.y + int(pant.height * 0.18)

    def mostrar(self):
        if self.ventana is None:
            return
        self.anterior = win.ventana_activa()
        self.mostrado_en = time.time()
        x, y = self._posicion()
        self.ventana.move(x, y)
        self.ventana.show()
        self.visible = True
        if not self.hwnd:
            try:
                self.hwnd = int(self.ventana.native.Handle.ToInt64())
                win.esquinas_redondeadas(self.hwnd)
            except Exception:  # noqa: BLE001
                pass
        win.traer_al_frente(self.hwnd)
        self.ventana.evaluate_js("relampago.mostrar()")

    def ocultar(self):
        if self.ventana is not None and self.visible:
            self.visible = False
            self.ventana.hide()

    def alternar(self):
        (self.ocultar if self.visible else self.mostrar)()

    def ajustar_alto(self, px: int):
        px = max(64, min(px, 640))
        if self.ventana is not None and abs(px - self.alto_actual) > 1:
            self.alto_actual = px
            self.ventana.resize(ANCHO, px)

    def pegar(self, texto: str):
        destino = self.anterior
        self.ocultar()
        threading.Thread(target=lambda: (time.sleep(0.08), win.pegar_en(destino, texto)), daemon=True).start()

    def recargar(self):
        self.config.clear()
        self.config.update(cargar_config())
        for p in self.motor.plugins:
            if p.nombre == "apps":
                threading.Thread(target=p.iniciar, daemon=True).start()
        return {"ocultar": False, "aviso": "Configuración recargada"}

    def salir(self):
        if self.atajo:
            self.atajo.detener()
        if self.ventana is not None:
            self.ventana.destroy()
        os._exit(0)

    # -------------------------------------------- arranque
    def _al_arrancar(self):
        self.motor.iniciar()
        self.atajo = win.AtajoGlobal(self.config.get("atajo", "alt+space"), self.alternar)
        if not self.atajo.iniciar():
            self.error_atajo = self.atajo.error
            win.notificar("relámpago: atajo ocupado", self.atajo.error or "")
            self.mostrar()
        elif "--mostrar" in sys.argv:
            self.mostrar()
        else:
            win.notificar("relámpago está listo", f"Pulsa {self.config['atajo'].title()} para abrirlo")

    def ejecutar(self):
        import webview
        x, y = self._posicion()
        self.ventana = webview.create_window(
            "relámpago", url=str(WEB / "index.html"), js_api=Api(self), width=ANCHO, height=72, x=x, y=y,
            frameless=True, on_top=True, resizable=False, hidden=True, focus=True, background_color="#16171d",
            easy_drag=False)
        webview.start(self._al_arrancar, private_mode=False, storage_path=str(HOME / "webview"))


def instancia_unica() -> bool:
    if not win.ES_WINDOWS:
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Local\\relampago-lanzador")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="relampago", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", action="store_true", help="arrancar con Windows")
    ap.add_argument("--no-inicio", action="store_true", help="no arrancar con Windows")
    ap.add_argument("--mostrar", action="store_true", help="mostrar la ventana al arrancar")
    ap.add_argument("--navegador", action="store_true", help="usar la interfaz en el navegador (pruebas)")
    ap.add_argument("--puerto", type=int, default=8765, help="puerto del modo navegador")
    a = ap.parse_args(argv)
    if sys.stdout is None or sys.stderr is None:  # pythonw: sin consola → a un log
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(HOME / "relampago.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stderr = log
    if a.inicio:
        print(instalar_inicio())
        return 0
    if a.no_inicio:
        print(quitar_inicio())
        return 0
    if a.navegador:
        from .navegador import servir
        import webbrowser
        servir(a.puerto)
        webbrowser.open(f"http://127.0.0.1:{a.puerto}")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    if not instancia_unica():
        print("relámpago ya está en marcha: pulsa", cargar_config()["atajo"])
        return 0
    Aplicacion().ejecutar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
