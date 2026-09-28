"""Precios de cripto en directo (API pública de Binance, sin clave):
'btc' · 'precio eth' · 'sol 12.5' (cuánto valen 12,5 SOL)."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

from ..nucleo import Plugin, Resultado
from .calculadora import dinero, formatear

MONEDAS = {
    "btc": "BTC", "bitcoin": "BTC", "eth": "ETH", "ethereum": "ETH", "ether": "ETH", "sol": "SOL",
    "solana": "SOL", "bnb": "BNB", "xrp": "XRP", "ripple": "XRP", "ada": "ADA", "cardano": "ADA",
    "doge": "DOGE", "dogecoin": "DOGE", "avax": "AVAX", "dot": "DOT", "polkadot": "DOT", "link": "LINK",
    "chainlink": "LINK", "ltc": "LTC", "litecoin": "LTC", "trx": "TRX", "ton": "TON", "sui": "SUI",
    "pepe": "PEPE", "shib": "SHIB", "near": "NEAR", "apt": "APT", "arb": "ARB", "op": "OP",
    "matic": "POL", "pol": "POL", "atom": "ATOM", "uni": "UNI", "aave": "AAVE", "inj": "INJ",
}
PATRON = re.compile(r"^(?:precio\s+(?:de\s+)?|price\s+)?([a-z]+)(?:\s+([\d.,]+))?\s*$", re.I)


class Cripto(Plugin):
    nombre = "cripto"
    titulo = "Cripto"
    ejemplo = "btc · precio eth · sol 12,5"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cache: dict[str, tuple[float, dict]] = {}
        self.cerrojo = threading.Lock()
        self.eur = (0.0, 0.0)  # (momento, EUR por USDT)

    def ticker(self, simbolo: str) -> dict:
        with self.cerrojo:
            c = self.cache.get(simbolo)
            if c and time.time() - c[0] < 15:
                return c[1]
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={simbolo}USDT"
        with urllib.request.urlopen(url, timeout=6) as r:
            d = json.loads(r.read())
        with self.cerrojo:
            self.cache[simbolo] = (time.time(), d)
        return d

    def eur_por_usdt(self) -> float | None:
        if time.time() - self.eur[0] < 300:
            return self.eur[1]
        try:
            with urllib.request.urlopen("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT", timeout=6) as r:
                v = 1 / float(json.loads(r.read())["price"])
            self.eur = (time.time(), v)
            return v
        except Exception:  # noqa: BLE001
            return None

    def buscar(self, consulta, empujar):
        m = PATRON.match(consulta.strip())
        if not m:
            return []
        palabra = m.group(1).lower()
        if palabra not in MONEDAS:
            return []
        if palabra in ("op", "link", "uni", "ton", "sol", "near") and not (m.group(2) or consulta.lower().startswith(("precio", "price"))):
            puntos = 70  # palabras ambiguas: no taparle 'Opera' o 'Link' a una app
        else:
            puntos = 150
        simbolo = MONEDAS[palabra]
        cantidad = None
        if m.group(2):
            try:
                cantidad = float(m.group(2).replace(",", "."))
            except ValueError:
                return []

        def pedir():
            try:
                d = self.ticker(simbolo)
                precio = float(d["lastPrice"])
                cambio = float(d["priceChangePercent"])
                flecha = "▲" if cambio >= 0 else "▼"
                eur = self.eur_por_usdt()
                dec = 2 if precio >= 1 else 6
                sub = (f"{flecha} {cambio:+.2f} % en 24 h · máx {formatear(round(float(d['highPrice']), dec))} · "
                       f"mín {formatear(round(float(d['lowPrice']), dec))}")
                if cantidad is not None:
                    total = cantidad * precio
                    titulo = f"{formatear(cantidad)} {simbolo} = {dinero(total)} $"
                    if eur:
                        titulo += f"  ·  {dinero(total * eur)} €"
                    copiar = f"{total:.2f}"
                else:
                    titulo = f"{simbolo}  {formatear(round(precio, dec))} $"
                    if eur:
                        titulo += f"  ·  {formatear(round(precio * eur, dec))} €"
                    copiar = f"{precio:.{dec}f}"
                empujar([Resultado(titulo, sub, "₿" if simbolo == "BTC" else simbolo[:2], 1,
                                   copiar=copiar, puntuacion=puntos, accion_texto="Copiar precio",
                                   alt=lambda: __import__("webbrowser").open(
                                       f"https://www.tradingview.com/chart/?symbol=BINANCE:{simbolo}USDT"),
                                   alt_texto="Ver gráfico")])
            except Exception:  # noqa: BLE001
                empujar([Resultado(f"No se pudo consultar {simbolo}", "¿Sin conexión?", "⚠", puntuacion=puntos)])

        threading.Thread(target=pedir, daemon=True).start()
        return [Resultado(f"Consultando {simbolo}…", "Binance", "₿" if simbolo == "BTC" else simbolo[:2], 1,
                          puntuacion=puntos)]
