"""Núcleo del lanzador: resultados, búsqueda aproximada, aprendizaje de uso y motor de plugins."""
from __future__ import annotations

import json
import math
import os
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HOME = Path(os.environ.get("RELAMPAGO_HOME", Path.home() / ".relampago"))


def normalizar(s: str) -> str:
    """minúsculas y sin tildes: 'Cámara' → 'camara'."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def puntuar(consulta: str, texto: str) -> float:
    """0 = no coincide. Mayor = mejor. Ambos ya normalizados."""
    if not consulta:
        return 1.0
    if texto == consulta:
        return 120.0
    if texto.startswith(consulta):
        return 100.0 - min(len(texto) - len(consulta), 20) * 0.5
    palabras = texto.replace("-", " ").replace("_", " ").replace(".", " ").split()
    if any(p.startswith(consulta) for p in palabras):
        return 80.0
    iniciales = "".join(p[0] for p in palabras if p)
    if len(consulta) >= 2 and iniciales.startswith(consulta):
        return 75.0
    i = texto.find(consulta)
    if i >= 0:
        return 60.0 - min(i, 20) * 0.5
    # subsecuencia por palabras: 'vscode' → [v]isual [s]tudio [code]. Cada trozo debe empezar al
    # principio de una palabra; así 'btc' no encuentra 'su[bt]ítulos en dire[c]to'.
    if len(consulta) < 3:
        return 0.0
    j, trozos, anterior = 0, 0, -2
    for i, c in enumerate(texto):
        if j == len(consulta):
            break
        if c != consulta[j]:
            continue
        if i != anterior + 1:                       # empezaría un trozo nuevo
            if i > 0 and texto[i - 1] not in " -_.":
                continue                            # …pero no en inicio de palabra: saltar
            trozos += 1
        j += 1
        anterior = i
    if j == len(consulta):
        return max(15.0, 50.0 - trozos * 5)
    return 0.0


@dataclass
class Resultado:
    titulo: str
    subtitulo: str = ""
    icono: str = "•"                  # emoji o 1-2 letras
    color: int | None = None          # índice de color para el avatar (0-7)
    accion: Callable[[], object] | None = None
    alt: Callable[[], object] | None = None   # Ctrl+Enter
    alt_texto: str = ""
    accion_texto: str = "Abrir"
    puntuacion: float = 0.0
    clave: str = ""                   # para aprender el uso (vacío = no aprender)
    pegar: str | None = None          # si no es None, Enter pega este texto en la ventana anterior
    copiar: str | None = None         # si no es None, Enter copia este texto
    mantener: bool = False            # no ocultar la ventana al ejecutar
    confirmar: str = ""               # pedir un segundo Enter con este aviso
    detalle: str = ""                 # texto largo (respuestas de IA, vista previa)
    completar: str = ""               # Tab rellena la barra con esto

    def publico(self, id_: int) -> dict:
        hace_algo = self.accion or self.pegar is not None or self.copiar is not None
        return {"id": id_, "titulo": self.titulo, "subtitulo": self.subtitulo, "icono": self.icono,
                "color": self.color, "accion": self.accion_texto if hace_algo else "",
                "alt": self.alt_texto if self.alt else "",
                "confirmar": self.confirmar, "detalle": self.detalle, "completar": self.completar}


class Uso:
    """Recuerda qué eliges para cada cosa y lo sube en los resultados (frecuencia + recencia)."""

    def __init__(self, ruta: Path | None = None):
        self.ruta = ruta or HOME / "uso.json"
        self.datos: dict[str, list[float]] = {}
        self._cerrojo = threading.Lock()
        try:
            self.datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def registrar(self, clave: str):
        if not clave:
            return
        with self._cerrojo:
            n, _ = self.datos.get(clave, [0, 0])
            self.datos[clave] = [n + 1, time.time()]
            try:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                self.ruta.write_text(json.dumps(self.datos), encoding="utf-8")
            except OSError:
                pass

    def extra(self, clave: str) -> float:
        d = self.datos.get(clave)
        if not d:
            return 0.0
        n, t = d
        dias = (time.time() - t) / 86400
        return min(35.0, 12 * math.log2(1 + n)) + max(0.0, 10 - dias)


class Plugin:
    """Un plugin responde a consultas. `prefijos` lo activa en exclusiva ('? ', 'cb ')."""
    nombre = "plugin"
    titulo = ""            # nombre legible para la pantalla de ayuda
    prefijos: tuple[str, ...] = ()
    ejemplo = ""           # se muestra en la pantalla de ayuda
    en_general = True      # participa en búsquedas sin prefijo

    def __init__(self, contexto: "Contexto"):
        self.ctx = contexto
        self.exclusivo = False  # True mientras responde a su propio prefijo

    def iniciar(self):
        """Carga en segundo plano (índices, etc.)."""

    def buscar(self, consulta: str, empujar: Callable[[list[Resultado]], None]) -> list[Resultado]:
        """Devuelve resultados inmediatos. Para resultados lentos (red, IA) llama a
        `empujar(lista)` más tarde desde otro hilo: reemplaza los resultados de este plugin."""
        return []


@dataclass
class Contexto:
    config: dict
    uso: Uso
    pegar: Callable[[str], None] = lambda t: None
    copiar: Callable[[str], None] = lambda t: None
    notificar: Callable[[str, str], None] = lambda t, m: None
    ocultar: Callable[[], None] = lambda: None
    refrescar: Callable[[], None] = lambda: None   # repetir la búsqueda actual
    extras: dict = field(default_factory=dict)


class Motor:
    def __init__(self, contexto: Contexto, plugins: list[type[Plugin]]):
        self.ctx = contexto
        self.plugins = [p(contexto) for p in plugins]
        self.actual: dict[int, Resultado] = {}
        self.consulta_id = 0
        self._por_plugin: dict[str, list[Resultado]] = {}
        self._cerrojo = threading.Lock()
        self.al_actualizar: Callable[[int, list[dict]], None] = lambda cid, r: None

    def iniciar(self):
        for p in self.plugins:
            threading.Thread(target=self._iniciar_seguro, args=(p,), daemon=True).start()

    @staticmethod
    def _iniciar_seguro(p: Plugin):
        try:
            p.iniciar()
        except Exception as e:  # noqa: BLE001 — un plugin roto no tumba el lanzador
            print(f"[{p.nombre}] no se pudo iniciar: {e}")

    def _elegir(self, texto: str) -> tuple[list[Plugin], str, bool]:
        """(plugins que responden, consulta sin prefijo, ¿vino por prefijo?)"""
        bajo = texto.lower()
        for p in self.plugins:
            for pre in p.prefijos:
                # 'cb ' se activa con "cb algo" y también con "cb" a secas
                if bajo.startswith(pre) or bajo == pre.strip():
                    return [p], texto[len(pre):].strip(), True
        return [p for p in self.plugins if p.en_general], texto.strip(), False

    def buscar(self, texto: str, limite: int = 9) -> tuple[int, list[dict]]:
        with self._cerrojo:
            self.consulta_id += 1
            cid = self.consulta_id
            self._por_plugin = {}
        elegidos, consulta, exclusivo = self._elegir(texto)
        for p in elegidos:
            p.exclusivo = exclusivo
            def empujar(res, p=p, cid=cid):
                with self._cerrojo:
                    if cid != self.consulta_id:
                        return  # llegó tarde: el usuario ya escribió otra cosa
                    self._por_plugin[p.nombre] = res
                self.al_actualizar(cid, self._componer(limite))
            try:
                res = p.buscar(consulta, empujar)
            except Exception as e:  # noqa: BLE001
                res = [Resultado(f"Error en {p.nombre}", str(e), "⚠")]
            with self._cerrojo:
                if p.nombre not in self._por_plugin:
                    self._por_plugin[p.nombre] = res
        return cid, self._componer(limite)

    def _componer(self, limite: int) -> list[dict]:
        with self._cerrojo:
            todos = [r for rs in self._por_plugin.values() for r in rs]
        for r in todos:
            r._total = r.puntuacion + self.ctx.uso.extra(r.clave)  # type: ignore[attr-defined]
        todos.sort(key=lambda r: r._total, reverse=True)  # type: ignore[attr-defined]
        todos = todos[:limite]
        with self._cerrojo:
            self.actual = dict(enumerate(todos))
        return [r.publico(i) for i, r in enumerate(todos)]

    def ejecutar(self, id_: int, alternativa: bool = False) -> dict:
        r = self.actual.get(id_)
        if r is None:
            return {"ok": False}
        self.ctx.uso.registrar(r.clave)
        if alternativa and r.alt:
            r.alt()
            return {"ok": True, "ocultar": not r.mantener}
        if r.pegar is not None:
            self.ctx.pegar(r.pegar)
            return {"ok": True, "ocultar": False}  # pegar ya oculta la ventana
        if r.copiar is not None:
            self.ctx.copiar(r.copiar)
            self.ctx.notificar("Copiado", r.copiar[:80])
            return {"ok": True, "ocultar": True, "aviso": "Copiado"}
        if r.accion:
            salida = r.accion()
            if isinstance(salida, dict):
                return {"ok": True, **salida}
        return {"ok": True, "ocultar": not r.mantener}
