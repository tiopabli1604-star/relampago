"""'ram': qué programas se comen la memoria (agrupados: 30 procesos de Chrome = 1 línea).
Enter en uno lo cierra (con confirmación)."""
from __future__ import annotations

import psutil

from ..nucleo import Plugin, Resultado, normalizar
from .calculadora import formatear

PROTEGIDOS = {"system", "registry", "smss", "csrss", "wininit", "winlogon", "services", "lsass", "svchost",
              "dwm", "explorer", "memcompression", "memory compression", "system idle process", "fontdrvhost",
              "sihost", "ctfmon", "searchhost", "startmenuexperiencehost", "msmpeng", "securityhealthservice",
              "python", "pythonw", "relampago"}


def grupos() -> list[tuple[str, int, list[psutil.Process]]]:
    g: dict[str, list] = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        mi = p.info.get("memory_info")
        nombre = (p.info.get("name") or "").lower().removesuffix(".exe")
        if not nombre or not mi:
            continue
        e = g.setdefault(nombre, [0, []])
        e[0] += mi.rss
        e[1].append(p)
    return sorted(((n, v[0], v[1]) for n, v in g.items()), key=lambda x: -x[1])


def cerrar(procs: list[psutil.Process]) -> int:
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, vivos = psutil.wait_procs(procs, timeout=3)
    for p in vivos:
        try:
            p.kill()
        except psutil.Error:
            pass
    return len(procs)


class Memoria(Plugin):
    nombre = "memoria"
    titulo = "Memoria RAM"
    prefijos = ("ram ", "memoria ")
    en_general = False
    ejemplo = "ram"

    def buscar(self, consulta, empujar):
        vm = psutil.virtual_memory()
        usado = (vm.total - vm.available) / 1024 ** 3
        cabecera = Resultado(f"RAM al {vm.percent:.0f} %  ·  {usado:.1f} de {vm.total / 1024 ** 3:.1f} GB",
                             "Enter en un programa para cerrarlo (todas sus ventanas)", "▤", 3, puntuacion=1000,
                             mantener=True)
        q = normalizar(consulta)
        salida = [cabecera]
        for nombre, rss, procs in grupos()[:40]:
            if q and q not in nombre:
                continue
            mb = rss / 1024 ** 2
            protegido = nombre in PROTEGIDOS
            sub = f"{len(procs)} proceso{'s' if len(procs) > 1 else ''}" + (" · del sistema" if protegido else "")
            titulo = f"{nombre}  —  {formatear(round(mb))} MB" if mb < 1024 else f"{nombre}  —  {mb / 1024:.1f} GB"
            if protegido:
                salida.append(Resultado(titulo, sub, "⚙", 4, puntuacion=900 - len(salida), mantener=True))
            else:
                salida.append(Resultado(
                    titulo, sub, nombre[:2].capitalize(), 7,
                    accion=lambda procs=procs, n=nombre: {"ocultar": False, "aviso": f"Cerrados {cerrar(procs)} procesos de {n}", "refrescar": True},
                    confirmar=f"¿Cerrar {nombre}? Se perderá lo que no hayas guardado. Enter otra vez",
                    puntuacion=900 - len(salida), mantener=True, accion_texto="Cerrar"))
            if len(salida) >= 12:
                break
        return salida
