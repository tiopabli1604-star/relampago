"""Historial del portapapeles: 'cb' lista lo último que copiaste, 'cb factura' filtra.
Enter lo pega en la ventana donde estabas. Respeta a los gestores de contraseñas: lo que
copian KeePass/Bitwarden/1Password viene marcado como privado y NO se guarda."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime

from ..nucleo import HOME, Plugin, Resultado, normalizar, puntuar
from .. import win

ARCHIVO = HOME / "portapapeles.json"
MAXIMO = 300
MAX_LARGO = 20_000


def hace(t: float) -> str:
    s = time.time() - t
    if s < 60:
        return "ahora"
    if s < 3600:
        return f"hace {int(s // 60)} min"
    if s < 86400:
        return f"hace {int(s // 3600)} h"
    return datetime.fromtimestamp(t).strftime("%d/%m %H:%M")


def resumen(texto: str, n: int = 90) -> str:
    una = " ".join(texto.split())
    return una if len(una) <= n else una[: n - 1] + "…"


class Portapapeles(Plugin):
    nombre = "portapapeles"
    titulo = "Portapapeles"
    prefijos = ("cb ", "pp ")
    en_general = False
    ejemplo = "cb · cb factura"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.items: list[dict] = []
        self.cerrojo = threading.Lock()
        self.activo = ctx.config.get("portapapeles", True)
        try:
            self.items = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self._propio: str | None = None  # lo que copia el propio lanzador no se re-guarda arriba

    def iniciar(self):
        if not self.activo or not win.ES_WINDOWS:
            return
        ultima = win.secuencia_portapapeles()
        while True:
            time.sleep(0.5)
            sec = win.secuencia_portapapeles()
            if sec == ultima:
                continue
            ultima = sec
            try:
                if win.portapapeles_privado():
                    continue
                texto = win.leer_portapapeles()
            except OSError:
                continue
            if texto and texto.strip() and len(texto) <= MAX_LARGO:
                self.añadir(texto)

    def añadir(self, texto: str):
        with self.cerrojo:
            self.items = [i for i in self.items if i["texto"] != texto]
            self.items.insert(0, {"texto": texto, "t": time.time()})
            del self.items[MAXIMO:]
            self._guardar()

    def borrar_todo(self):
        with self.cerrojo:
            self.items = []
            self._guardar()
        return {"ocultar": False, "limpiar": True}

    def _guardar(self):
        try:
            ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
            ARCHIVO.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def buscar(self, consulta, empujar):
        if not self.activo:
            return [Resultado("Historial del portapapeles desactivado", "Actívalo en la configuración", "📋")]
        q = normalizar(consulta)
        with self.cerrojo:
            items = list(self.items)
        salida = []
        for n, it in enumerate(items):
            s = 300 - n if not q else puntuar(q, normalizar(it["texto"][:500]))
            if s <= 0:
                continue
            texto = it["texto"]
            lineas = texto.count("\n") + 1
            sub = hace(it["t"]) + (f" · {lineas} líneas" if lineas > 1 else "") + f" · {len(texto)} caracteres"
            salida.append(Resultado(resumen(texto), sub, "📋", 7, pegar=texto, accion_texto="Pegar",
                                    alt=lambda t=texto: self.ctx.copiar(t), alt_texto="Solo copiar",
                                    detalle=texto if lineas > 1 or len(texto) > 90 else "",
                                    puntuacion=s + 100))
            if len(salida) >= 30:
                break
        if not salida:
            salida.append(Resultado("Nada en el historial" if not items else "Sin coincidencias",
                                    "Copia algo (Ctrl+C) y aparecerá aquí", "📋", puntuacion=100))
        if not q and items:
            salida.append(Resultado("Borrar historial del portapapeles", f"{len(items)} elementos", "🗑", 7,
                                    accion=self.borrar_todo, confirmar="¿Borrar todo el historial? Enter otra vez",
                                    mantener=True, puntuacion=1))
        return salida
