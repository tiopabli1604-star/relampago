"""Temporizadores y alarmas con notificación de Windows:
't 25m' · 't 1h30m sacar la ropa' · 't 10:30 reunión' · 't' lista los activos (Enter cancela)."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta

from ..nucleo import Plugin, Resultado
from .. import win

HORA = re.compile(r"^(\d{1,2})[:.h](\d{2})(?:\s+(.*))?$")
# '1h30m', '1h 30m', '25m', '90s', '2 h', '25 min' seguidos de una etiqueta opcional
_UNIDAD = r"(?:horas?|h|minutos?|min|m|segundos?|seg|s)(?=\d|\s|$)"
DURACION = re.compile(rf"^((?:\d+\s*{_UNIDAD}\s*)+)(.*)$", re.I)
TROZO = re.compile(rf"(\d+)\s*({_UNIDAD})", re.I)
FACTOR = {"h": 3600, "m": 60, "s": 1}


def parsear(texto: str) -> tuple[float, str] | None:
    """'25m tarea' → (segundos, 'tarea'); '10:30 reunión' → (segundos hasta las 10:30, 'reunión');
    '5' → 5 minutos."""
    texto = texto.strip()
    m = HORA.match(texto)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None
        ahora = datetime.now()
        objetivo = ahora.replace(hour=h, minute=mi, second=0, microsecond=0)
        if objetivo <= ahora:
            objetivo += timedelta(days=1)
        return (objetivo - ahora).total_seconds(), (m.group(3) or "").strip()
    m = DURACION.match(texto)
    if m:
        total = sum(int(n) * FACTOR[u[0].lower()] for n, u in TROZO.findall(m.group(1)))
        return (float(total), m.group(2).strip()) if total > 0 else None
    m = re.match(r"^(\d+)(?:\s+(.*))?$", texto)
    if m:  # número suelto = minutos
        return int(m.group(1)) * 60.0, (m.group(2) or "").strip()
    return None


def legible(seg: float) -> str:
    seg = int(round(seg))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s" if m < 10 else f"{m} min"
    return f"{s} s"


class Temporizador(Plugin):
    nombre = "temporizador"
    titulo = "Temporizador"
    prefijos = ("t ", "timer ", "alarma ")
    en_general = False
    ejemplo = "t 25m · t 10:30 reunión"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.activos: dict[int, dict] = {}
        self.siguiente = 1
        self.cerrojo = threading.Lock()

    def crear(self, segundos: float, etiqueta: str) -> dict:
        with self.cerrojo:
            n = self.siguiente
            self.siguiente += 1
            fin = time.time() + segundos
            cancelar = threading.Event()
            self.activos[n] = {"fin": fin, "etiqueta": etiqueta, "cancelar": cancelar}

        def esperar():
            if cancelar.wait(segundos):
                return
            with self.cerrojo:
                self.activos.pop(n, None)
            win.notificar("⏰ " + (etiqueta or "¡Tiempo!"), f"Temporizador de {legible(segundos)} terminado",
                          sonido=True)

        threading.Thread(target=esperar, daemon=True).start()
        hora = datetime.fromtimestamp(fin).strftime("%H:%M")
        return {"ocultar": True, "aviso": f"Temporizador hasta las {hora}"}

    def cancelar(self, n: int) -> dict:
        with self.cerrojo:
            t = self.activos.pop(n, None)
        if t:
            t["cancelar"].set()
        return {"ocultar": False, "refrescar": True, "aviso": "Cancelado"}

    def buscar(self, consulta, empujar):
        salida = []
        r = parsear(consulta) if consulta else None
        if r:
            seg, etiqueta = r
            hora = (datetime.now() + timedelta(seconds=seg)).strftime("%H:%M")
            salida.append(Resultado(f"Temporizador de {legible(seg)}" + (f": {etiqueta}" if etiqueta else ""),
                                    f"Sonará a las {hora}", "⏱", 3,
                                    accion=lambda: self.crear(seg, etiqueta), puntuacion=300,
                                    accion_texto="Empezar"))
        elif consulta:
            salida.append(Resultado("Formato: t 25m · t 1h30m texto · t 10:30 reunión", "", "⏱", puntuacion=300))
        with self.cerrojo:
            activos = sorted(self.activos.items(), key=lambda kv: kv[1]["fin"])
        for n, t in activos:
            queda = t["fin"] - time.time()
            salida.append(Resultado(f"{legible(queda)} restantes" + (f" · {t['etiqueta']}" if t["etiqueta"] else ""),
                                    f"Termina a las {datetime.fromtimestamp(t['fin']).strftime('%H:%M:%S')} · "
                                    "Enter para cancelar", "⏳", 3, accion=lambda n=n: self.cancelar(n),
                                    mantener=True, puntuacion=200, accion_texto="Cancelar"))
        if not salida:
            salida.append(Resultado("No hay temporizadores activos", "Ejemplo: t 25m pomodoro", "⏱", puntuacion=100))
        return salida
