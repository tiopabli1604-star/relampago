"""Conversión de unidades y divisas: '10 km a millas' · '30 c a f' · '100 usd a eur' · '5 gb en mb'"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

from ..nucleo import Plugin, Resultado
from .calculadora import dinero, formatear, para_copiar

# unidad → (magnitud, factor a la unidad base)
U: dict[str, tuple[str, float]] = {}


def _def(magnitud: str, factor: float, *nombres: str):
    for n in nombres:
        U[n] = (magnitud, factor)


_def("longitud", 1, "m", "metro", "metros")
_def("longitud", 1000, "km", "kilometro", "kilómetro", "kilometros", "kilómetros")
_def("longitud", 0.01, "cm", "centimetro", "centímetro", "centimetros", "centímetros")
_def("longitud", 0.001, "mm", "milimetro", "milímetro", "milimetros", "milímetros")
_def("longitud", 1609.344, "mi", "milla", "millas", "mile", "miles")
_def("longitud", 0.3048, "ft", "pie", "pies", "feet", "foot")
_def("longitud", 0.0254, "in", "pulgada", "pulgadas", "inch", "inches", '"')
_def("longitud", 0.9144, "yd", "yarda", "yardas")
_def("longitud", 1852, "nmi", "milla nautica", "millas nauticas")
_def("masa", 1, "kg", "kilo", "kilos", "kilogramo", "kilogramos")
_def("masa", 0.001, "g", "gramo", "gramos")
_def("masa", 1e-6, "mg", "miligramo", "miligramos")
_def("masa", 1000, "t", "tonelada", "toneladas")
_def("masa", 0.45359237, "lb", "lbs", "libra", "libras", "pound", "pounds")
_def("masa", 0.028349523125, "oz", "onza", "onzas", "ounce", "ounces")
_def("volumen", 1, "l", "litro", "litros")
_def("volumen", 0.001, "ml", "mililitro", "mililitros")
_def("volumen", 3.785411784, "gal", "galon", "galón", "galones", "gallon", "gallons")
_def("volumen", 0.2365882365, "taza", "tazas", "cup", "cups")
_def("volumen", 1000, "m3", "metro cubico", "metros cubicos")
_def("datos", 1, "b", "byte", "bytes")
_def("datos", 1024, "kb", "kib")
_def("datos", 1024 ** 2, "mb", "mib", "megas")
_def("datos", 1024 ** 3, "gb", "gib", "gigas")
_def("datos", 1024 ** 4, "tb", "tib", "teras")
_def("tiempo", 1, "s", "seg", "segundo", "segundos")
_def("tiempo", 60, "min", "minuto", "minutos")
_def("tiempo", 3600, "h", "hora", "horas")
_def("tiempo", 86400, "d", "dia", "día", "dias", "días")
_def("tiempo", 604800, "semana", "semanas")
_def("tiempo", 31557600, "año", "años", "ano", "anos")
_def("velocidad", 1, "m/s")
_def("velocidad", 1 / 3.6, "km/h", "kmh")
_def("velocidad", 0.44704, "mph")
_def("velocidad", 0.514444, "nudo", "nudos", "kn")
_def("area", 1, "m2", "metro cuadrado", "metros cuadrados")
_def("area", 10000, "ha", "hectarea", "hectárea", "hectareas", "hectáreas")
_def("area", 1e6, "km2")
_def("area", 0.09290304, "ft2", "pie cuadrado", "pies cuadrados")
_def("area", 4046.8564224, "acre", "acres")
TEMP = {"c": "C", "celsius": "C", "ºc": "C", "°c": "C", "f": "F", "fahrenheit": "F", "ºf": "F", "°f": "F",
        "k": "K", "kelvin": "K"}

DIVISAS = {"eur", "usd", "gbp", "jpy", "chf", "cad", "aud", "cny", "mxn", "brl", "ars", "clp", "cop",
           "sek", "nok", "dkk", "pln", "czk", "huf", "try", "inr", "krw", "sgd", "hkd", "nzd", "zar",
           "ron", "bgn", "isk", "ils", "thb", "php", "idr", "myr"}
ALIAS_DIVISA = {"euro": "eur", "euros": "eur", "€": "eur", "dolar": "usd", "dólar": "usd", "dolares": "usd",
                "dólares": "usd", "$": "usd", "libra esterlina": "gbp", "libras esterlinas": "gbp",
                "yen": "jpy", "yenes": "jpy", "peso mexicano": "mxn", "pesos mexicanos": "mxn",
                "£": "gbp", "franco suizo": "chf"}

PATRON = re.compile(r"^\s*([\d.,]+)\s*([^\d]+?)\s+(?:a|en|to|in|->|=)\s+(.+?)\s*$", re.I)


def convertir_temp(v: float, de: str, a: str) -> float:
    c = {"C": v, "F": (v - 32) * 5 / 9, "K": v - 273.15}[de]
    return {"C": c, "F": c * 9 / 5 + 32, "K": c + 273.15}[a]


def numero(txt: str) -> float:
    txt = txt.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", txt):
        txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", ".")
    return float(txt)


def convertir(texto: str) -> tuple[float, str, str, float] | None:
    """Solo unidades (las divisas van por red). Devuelve (valor, de, a, resultado)."""
    m = PATRON.match(texto)
    if not m:
        return None
    v = numero(m.group(1))
    de, a = m.group(2).strip().lower(), m.group(3).strip().lower()
    if de in TEMP and a in TEMP:
        return v, TEMP[de], TEMP[a], convertir_temp(v, TEMP[de], TEMP[a])
    if de in U and a in U and U[de][0] == U[a][0]:
        return v, de, a, v * U[de][1] / U[a][1]
    return None


class Tasas:
    """Tipos de cambio del BCE (frankfurter.app), cacheados 1 hora."""

    def __init__(self):
        self.cache: dict[str, tuple[float, dict]] = {}
        self.cerrojo = threading.Lock()

    def obtener(self, base: str) -> dict:
        base = base.upper()
        with self.cerrojo:
            c = self.cache.get(base)
            if c and time.time() - c[0] < 3600:
                return c[1]
        req = urllib.request.Request(f"https://api.frankfurter.dev/v1/latest?base={base}",
                                     headers={"User-Agent": "relampago/0.1 (+https://github.com)"})
        with urllib.request.urlopen(req, timeout=6) as r:
            datos = json.loads(r.read())["rates"]
        with self.cerrojo:
            self.cache[base] = (time.time(), datos)
        return datos


class Conversor(Plugin):
    nombre = "conversor"
    titulo = "Conversor"
    ejemplo = "10 km a millas · 30 c a f · 100 usd a eur"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.tasas = Tasas()

    def buscar(self, consulta, empujar):
        m = PATRON.match(consulta)
        if not m:
            return []
        try:
            r = convertir(consulta)
        except ValueError:
            return []
        if r:
            v, de, a, res = r
            return [Resultado(f"{formatear(round(res, 6))} {a}", f"{formatear(v)} {de} = {formatear(res)} {a}",
                              "⇄", 2, copiar=para_copiar(round(res, 6)), puntuacion=190, accion_texto="Copiar")]
        de = ALIAS_DIVISA.get(m.group(2).strip().lower(), m.group(2).strip().lower())
        a = ALIAS_DIVISA.get(m.group(3).strip().lower(), m.group(3).strip().lower())
        if de not in DIVISAS or a not in DIVISAS:
            return []
        try:
            v = numero(m.group(1))
        except ValueError:
            return []

        def pedir():
            try:
                tasas = {} if de == a else self.tasas.obtener(de)
                if de != a and a.upper() not in tasas:
                    empujar([Resultado(f"El BCE no publica el cambio {de.upper()} → {a.upper()}",
                                       "Prueba con EUR o USD como intermedio", "€", 2, puntuacion=190)])
                    return
                tasa = 1.0 if de == a else tasas[a.upper()]
                res = v * tasa
                empujar([Resultado(f"{dinero(res)} {a.upper()}",
                                   f"{formatear(v)} {de.upper()} · 1 {de.upper()} = {formatear(round(tasa, 5))} "
                                   f"{a.upper()} (BCE)", "€", 2, copiar=para_copiar(round(res, 2)),
                                   puntuacion=190, accion_texto="Copiar")])
            except Exception:  # noqa: BLE001
                empujar([Resultado("No se pudo obtener el tipo de cambio", "¿Sin conexión?", "⚠", puntuacion=190)])

        threading.Thread(target=pedir, daemon=True).start()
        return [Resultado("Consultando tipo de cambio…", f"{m.group(1)} {de.upper()} → {a.upper()}", "€", 2,
                          puntuacion=190)]
