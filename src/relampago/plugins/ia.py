"""Pregunta a tu IA local (Ollama): '? cómo hago un left join' — sin internet, gratis y privado.
La respuesta aparece en streaming; Enter la copia. Recuerda la conversación hasta que la borras."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from ..nucleo import Plugin, Resultado

OLLAMA = "http://127.0.0.1:11434"
SISTEMA = ("Eres un asistente integrado en un lanzador de escritorio. Responde en el idioma de la pregunta "
           "(normalmente español), directo y breve: primero la respuesta, luego lo imprescindible. "
           "Si piden código, da solo el código mínimo con un comentario corto.")


def modelos() -> list[str]:
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as r:
        return [m["name"] for m in json.loads(r.read()).get("models", [])]


class IA(Plugin):
    nombre = "ia"
    titulo = "IA local"
    prefijos = ("?", "ia ")
    en_general = False
    ejemplo = "? cómo hago un left join en SQL"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.historial: list[dict] = []
        self.respuesta = ""
        self.pregunta = ""
        self.generando = False
        self._parar = threading.Event()

    def modelo(self) -> str | None:
        preferido = self.ctx.config.get("modelo_ia")
        try:
            disponibles = modelos()
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if preferido and preferido in disponibles:
            return preferido
        for pref in ("qwen2.5", "llama3", "gemma", "mistral", "phi"):
            for m in disponibles:
                if m.startswith(pref) and "embed" not in m:
                    return m
        return disponibles[0] if disponibles else None

    def _res_respuesta(self, modelo: str) -> Resultado:
        estado = "escribiendo…" if self.generando else "Enter copia · Ctrl+Enter nueva conversación"
        return Resultado(self.pregunta, f"{modelo} · {estado}", "✦", 6, detalle=self.respuesta or "…",
                         copiar=self.respuesta if not self.generando else None, mantener=True,
                         accion_texto="Copiar respuesta", puntuacion=500,
                         alt=self.olvidar, alt_texto="Nueva conversación")

    def olvidar(self):
        self._parar.set()
        self.historial, self.respuesta, self.pregunta = [], "", ""
        return {"ocultar": False, "limpiar": True}

    def buscar(self, consulta, empujar):
        q = consulta.strip()
        if not q:
            if self.respuesta:
                return [self._res_respuesta(self.ctx.config.get("_modelo_actual", "IA"))]
            return [Resultado("Pregunta a tu IA local", "Escribe tu pregunta después de ?  ·  usa Ollama, "
                              "sin internet", "✦", 6, puntuacion=500)]
        if q == self.pregunta and (self.respuesta or self.generando):
            return [self._res_respuesta(self.ctx.config.get("_modelo_actual", "IA"))]

        def preguntar():
            modelo = self.modelo()
            if not modelo:
                empujar([Resultado("Ollama no está en marcha", "Ábrelo (o instala uno: ollama pull qwen2.5:7b)",
                                   "⚠", puntuacion=500)])
                return {"ocultar": False}
            self.ctx.config["_modelo_actual"] = modelo
            self._parar.clear()
            self.pregunta, self.respuesta, self.generando = q, "", True
            self.historial.append({"role": "user", "content": q})
            empujar([self._res_respuesta(modelo)])
            threading.Thread(target=self._stream, args=(modelo, empujar), daemon=True).start()
            return {"ocultar": False}

        turnos = len(self.historial) // 2
        sub = "Enter para preguntar" + (f" · sigue la conversación ({turnos} turnos)" if turnos else "")
        return [Resultado(q, sub, "✦", 6, accion=preguntar, mantener=True, accion_texto="Preguntar",
                          puntuacion=500, alt=self.olvidar, alt_texto="Nueva conversación")]

    def _stream(self, modelo: str, empujar):
        cuerpo = json.dumps({"model": modelo, "stream": True,
                             "messages": [{"role": "system", "content": SISTEMA}, *self.historial[-12:]]}).encode()
        req = urllib.request.Request(OLLAMA + "/api/chat", data=cuerpo, headers={"Content-Type": "application/json"})
        ultimo = 0
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                for linea in r:
                    if self._parar.is_set():
                        break
                    d = json.loads(linea)
                    self.respuesta += d.get("message", {}).get("content", "")
                    if len(self.respuesta) - ultimo > 12 or d.get("done"):
                        ultimo = len(self.respuesta)
                        empujar([self._res_respuesta(modelo)])
                    if d.get("done"):
                        break
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.respuesta += f"\n\n[error: {e}]"
        self.generando = False
        if self.respuesta:
            self.historial.append({"role": "assistant", "content": self.respuesta})
        empujar([self._res_respuesta(modelo)])
