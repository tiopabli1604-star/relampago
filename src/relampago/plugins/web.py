"""Búsquedas web con atajos: 'g receta paella' · 'yt lofi' · 'gh ccxt' · 'wiki roma' · 'tr hello'
También abre direcciones escritas tal cual: 'github.com/tiopabli1604-star'."""
from __future__ import annotations

import re
import webbrowser
from urllib.parse import quote_plus

from ..nucleo import Plugin, Resultado

MOTORES = {
    "g": ("Google", "https://www.google.com/search?q={}", "G", 0),
    "yt": ("YouTube", "https://www.youtube.com/results?search_query={}", "▶", 7),
    "gh": ("GitHub", "https://github.com/search?q={}&type=repositories", "GH", 6),
    "wiki": ("Wikipedia", "https://es.wikipedia.org/w/index.php?search={}", "W", 5),
    "tr": ("Traductor", "https://translate.google.com/?sl=auto&tl=es&text={}", "文", 2),
    "en": ("Traducir al inglés", "https://translate.google.com/?sl=auto&tl=en&text={}", "文", 2),
    "maps": ("Google Maps", "https://www.google.com/maps/search/{}", "📍", 3),
    "so": ("Stack Overflow", "https://stackoverflow.com/search?q={}", "SO", 1),
    "pypi": ("PyPI", "https://pypi.org/search/?q={}", "Py", 0),
    "npm": ("npm", "https://www.npmjs.com/search?q={}", "np", 7),
    "tv": ("TradingView", "https://www.tradingview.com/chart/?symbol={}", "TV", 0),
    "amz": ("Amazon", "https://www.amazon.es/s?k={}", "a", 1),
    "rae": ("Diccionario RAE", "https://dle.rae.es/{}", "Ñ", 7),
    "chat": ("ChatGPT", "https://chatgpt.com/?q={}", "✦", 2),
    "claude": ("Claude", "https://claude.ai/new?q={}", "✦", 1),
}
URL = re.compile(r"^(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$", re.I)


class Web(Plugin):
    nombre = "web"
    titulo = "Buscar en web"
    ejemplo = "g receta paella · yt lofi · gh ccxt · tr good morning"

    def buscar(self, consulta, empujar):
        q = consulta.strip()
        if not q:
            return []
        partes = q.split(maxsplit=1)
        clave = partes[0].lower()
        if clave in MOTORES and len(partes) == 2:
            nombre, url, icono, color = MOTORES[clave]
            destino = url.format(quote_plus(partes[1]))
            return [Resultado(f"{nombre}: {partes[1]}", destino, icono, color,
                              accion=lambda: webbrowser.open(destino), puntuacion=180,
                              clave=f"web:{clave}", accion_texto="Buscar")]
        if URL.match(q) and " " not in q:
            destino = q if q.startswith("http") else "https://" + q
            return [Resultado(f"Abrir {q}", destino, "↗", 0, accion=lambda: webbrowser.open(destino),
                              puntuacion=170, accion_texto="Abrir")]
        # comodín: siempre ofrecer buscar en Google al final de la lista
        destino = MOTORES["g"][1].format(quote_plus(q))
        return [Resultado(f"Buscar «{q}» en Google", "g + texto para ir directo", "G", 0,
                          accion=lambda: webbrowser.open(destino), puntuacion=8, accion_texto="Buscar")]
