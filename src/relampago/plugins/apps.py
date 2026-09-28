"""Programas instalados: los mismos que ves en el menú Inicio (clásicos y de la Store)."""
from __future__ import annotations

import json
import subprocess
import zlib

from ..nucleo import HOME, Plugin, Resultado, normalizar, puntuar
from .. import win

CACHE = HOME / "apps.json"
IGNORAR = ("desinstalar", "uninstall", "readme", "léame", "help", "ayuda", "release notes",
           "documentation", "website", "sitio web")


def color_de(nombre: str) -> int:
    return zlib.crc32(nombre.encode()) % 8


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.replace("-", " ").split() if p[:1].isalnum()]
    if not partes:
        return nombre[:1].upper()
    if len(partes) == 1:
        return partes[0][:2].capitalize()
    return (partes[0][0] + partes[1][0]).upper()


def leer_apps_windows() -> list[dict]:
    """Get-StartApps devuelve nombre + AppID de todo lo que hay en Inicio."""
    cmd = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, encoding="utf-8", timeout=60, creationflags=0x08000000)
    datos = json.loads(r.stdout or "[]")
    if isinstance(datos, dict):
        datos = [datos]
    vistas, apps = set(), []
    for d in datos:
        nombre, appid = (d.get("Name") or "").strip(), d.get("AppID") or ""
        if not nombre or not appid or nombre.lower() in vistas:
            continue
        if any(x in nombre.lower() for x in IGNORAR):
            continue
        vistas.add(nombre.lower())
        apps.append({"nombre": nombre, "id": appid})
    return apps


class Apps(Plugin):
    nombre = "apps"
    titulo = "Programas"
    ejemplo = "chrome, notion, vsc"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.apps: list[dict] = []
        try:
            self.apps = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self._preparar()

    def _preparar(self):
        for a in self.apps:
            a["_n"] = normalizar(a["nombre"])

    def iniciar(self):
        if not win.ES_WINDOWS:
            return
        apps = leer_apps_windows()
        if apps:
            self.apps = apps
            self._preparar()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps([{"nombre": a["nombre"], "id": a["id"]} for a in apps],
                                        ensure_ascii=False), encoding="utf-8")

    def buscar(self, consulta, empujar):
        q = normalizar(consulta)
        if not q:
            return []
        salida = []
        for a in self.apps:
            s = puntuar(q, a["_n"])
            if s <= 0:
                continue
            appid = a["id"]
            salida.append(Resultado(
                a["nombre"], "Aplicación", iniciales(a["nombre"]), color_de(a["nombre"]),
                accion=lambda appid=appid: win.abrir(f"shell:AppsFolder\\{appid}"),
                puntuacion=s + 5, clave=f"app:{appid}", accion_texto="Abrir"))
        return sorted(salida, key=lambda r: -r.puntuacion)[:12]
