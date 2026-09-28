"""Buscar archivos y carpetas en tus carpetas habituales: 'f informe' (o sin prefijo, 3+ letras).
Enter abre · Ctrl+Enter muestra en el Explorador."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ..nucleo import Plugin, Resultado, normalizar, puntuar
from .. import win

SALTAR = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".cache", ".gradle", ".idea", "build",
          "dist", "target", ".next", "site-packages", ".pytest_cache", ".mypy_cache", ".ruff_cache",
          "AppData", "$RECYCLE.BIN", ".tox", "obj", "bin"}
ICONOS = {".pdf": "📕", ".doc": "📘", ".docx": "📘", ".xls": "📗", ".xlsx": "📗", ".csv": "📗",
          ".ppt": "📙", ".pptx": "📙", ".txt": "📄", ".md": "📄", ".py": "🐍", ".js": "📜", ".ts": "📜",
          ".html": "🌐", ".zip": "🗜", ".rar": "🗜", ".7z": "🗜", ".jpg": "🖼", ".jpeg": "🖼", ".png": "🖼",
          ".gif": "🖼", ".mp4": "🎬", ".mkv": "🎬", ".mp3": "🎵", ".exe": "⚙", ".msi": "⚙", ".sql": "🗃",
          ".java": "☕", ".json": "📜", ".lnk": "↗"}


def carpetas_por_defecto() -> list[str]:
    h = Path.home()
    base = [h / "Desktop", h / "Documents", h / "Downloads", h / "OneDrive" / "Escritorio",
            h / "OneDrive" / "Documentos", h / "Pictures", h / "Videos", h / "Music"]
    return [str(p) for p in base if p.is_dir()]


def indexar(raices: list[str], max_prof: int = 6, max_total: int = 200_000) -> list[tuple[str, str, bool]]:
    """(ruta, nombre_normalizado, es_carpeta)."""
    salida: list[tuple[str, str, bool]] = []
    for raiz in raices:
        pila = [(raiz, 0)]
        while pila and len(salida) < max_total:
            ruta, prof = pila.pop()
            try:
                with os.scandir(ruta) as it:
                    for e in it:
                        if e.name.startswith(".") and e.name not in (".env",):
                            continue
                        try:
                            es_dir = e.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if es_dir and e.name in SALTAR:
                            continue
                        salida.append((e.path, normalizar(e.name), es_dir))
                        if es_dir and prof < max_prof:
                            pila.append((e.path, prof + 1))
            except OSError:
                continue
    return salida


class Archivos(Plugin):
    nombre = "archivos"
    titulo = "Archivos"
    prefijos = ("f ", "archivo ", "abrir ")
    ejemplo = "f informe · archivo apuntes sql"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.indice: list[tuple[str, str, bool]] = []
        self.cerrojo = threading.Lock()
        self.listo = False

    def raices(self) -> list[str]:
        extra = [c for c in self.ctx.config.get("carpetas", []) if os.path.isdir(c)]
        return carpetas_por_defecto() + extra

    def iniciar(self):
        while True:
            nuevo = indexar(self.raices())
            with self.cerrojo:
                self.indice = nuevo
                self.listo = True
            time.sleep(600)  # reindexar cada 10 min

    def buscar(self, consulta, empujar):
        q = normalizar(consulta.strip())
        if len(q) < 3:
            return []
        with self.cerrojo:
            indice = self.indice
        candidatos = []
        palabras = q.split()
        for ruta, nombre, es_dir in indice:
            if not all(p in nombre for p in palabras):
                continue
            s = puntuar(q, nombre) if len(palabras) == 1 else 60.0
            if s <= 0:
                continue
            candidatos.append((s - len(ruta) / 200, ruta, es_dir))
            if len(candidatos) > 400:
                break
        candidatos.sort(reverse=True)
        salida = []
        for s, ruta, es_dir in candidatos[:15 if self.exclusivo else 4]:
            nombre = os.path.basename(ruta)
            ext = os.path.splitext(nombre)[1].lower()
            icono = "📁" if es_dir else ICONOS.get(ext, "📄")
            salida.append(Resultado(nombre, os.path.dirname(ruta), icono, 5,
                                    accion=lambda r=ruta: win.abrir(r),
                                    alt=lambda r=ruta: win.mostrar_en_carpeta(r), alt_texto="Mostrar en carpeta",
                                    puntuacion=s * 0.55, clave=f"f:{ruta}", accion_texto="Abrir"))
        return salida
