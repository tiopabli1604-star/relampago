"""Textos guardados que se pegan al instante: ';correo' · ';fecha' · ';uuid'.
Los tuyos van en ~/.relampago/config.json → "snippets": {"correo": "yo@ejemplo.com"}."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from ..nucleo import Plugin, Resultado, normalizar, puntuar

DINAMICOS = {
    "fecha": ("Fecha de hoy", lambda: datetime.now().strftime("%d/%m/%Y")),
    "hora": ("Hora actual", lambda: datetime.now().strftime("%H:%M")),
    "iso": ("Fecha ISO", lambda: datetime.now().strftime("%Y-%m-%d")),
    "ahora": ("Fecha y hora", lambda: datetime.now().strftime("%d/%m/%Y %H:%M")),
    "uuid": ("UUID nuevo", lambda: str(uuid.uuid4())),
    "clave": ("Contraseña aleatoria (20)", lambda: secrets.token_urlsafe(15)),
    "lorem": ("Lorem ipsum", lambda: "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
                                     "tempor incididunt ut labore et dolore magna aliqua."),
}


class Snippets(Plugin):
    nombre = "snippets"
    titulo = "Snippets"
    prefijos = (";",)
    en_general = False
    ejemplo = ";fecha · ;correo"

    def buscar(self, consulta, empujar):
        q = normalizar(consulta)
        propios = self.ctx.config.get("snippets", {})
        salida = []
        for clave, texto in propios.items():
            s = puntuar(q, normalizar(clave)) if q else 50
            if s > 0:
                salida.append(Resultado(f";{clave}", texto[:90], "✎", 5, pegar=texto, accion_texto="Pegar",
                                        puntuacion=s + 20, clave=f"snip:{clave}"))
        for clave, (desc, fn) in DINAMICOS.items():
            s = puntuar(q, clave) if q else 40
            if s > 0:
                valor = fn()
                salida.append(Resultado(f";{clave}  →  {valor[:60]}", desc, "✎", 5, pegar=valor,
                                        accion_texto="Pegar", puntuacion=s, clave=f"snip:{clave}"))
        if not propios and not q:
            salida.append(Resultado("Añade tus textos en la configuración", "escribe «ajustes» y Enter", "⚙",
                                    puntuacion=1))
        return salida
