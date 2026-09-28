"""Calculadora segura (sin eval): 2340*1.21 · 15% de 80 · 80 + 21% · sqrt(2) · 2^10 · 3,5*2"""
from __future__ import annotations

import ast
import math
import operator
import re

from ..nucleo import Plugin, Resultado

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
       ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {"sqrt": math.sqrt, "raiz": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
         "sen": math.sin, "log": math.log10, "ln": math.log, "abs": abs, "round": round,
         "redondear": round, "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
         "fact": math.factorial, "factorial": math.factorial}
CONST = {"pi": math.pi, "e": math.e, "tau": math.tau}
PARECE = re.compile(r"^[\d\s.,+\-*/%^()a-z]+$", re.I)


class ErrorCalculo(ValueError):
    pass


def _eval(n):
    if isinstance(n, ast.Expression):
        return _eval(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        a, b = _eval(n.left), _eval(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e6 and b > 10):
            raise ErrorCalculo("número demasiado grande")
        return OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](_eval(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
        args = [_eval(a) for a in n.args]
        if n.func.id in ("fact", "factorial") and args and args[0] > 500:
            raise ErrorCalculo("número demasiado grande")
        return FUNCS[n.func.id](*args)
    if isinstance(n, ast.Name) and n.id in CONST:
        return CONST[n.id]
    raise ErrorCalculo("expresión no permitida")


def preparar(texto: str) -> str:
    t = texto.strip().lower().replace("×", "*").replace("÷", "/").replace("^", "**")
    t = t.replace("x", "*") if re.fullmatch(r"[\d.,\s]+x[\d.,\s]+", t) else t
    # coma decimal española: "3,5" → "3.5" (pero "1,234,567" → miles)
    if re.search(r"\d,\d{3},\d{3}", t):
        t = t.replace(",", "")
    else:
        t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    # 15% de 80  → (15/100)*80
    t = re.sub(r"([\d.]+)\s*%\s*(de|of)\s*", r"(\1/100)*", t)
    # 80 + 21%  → 80*(1+21/100)   ·   80 - 15% → 80*(1-15/100)
    t = re.sub(r"^(.+?)\s*([+-])\s*([\d.]+)\s*%$", r"(\1)*(1\2\3/100)", t)
    # 21%  → 0.21
    t = re.sub(r"([\d.]+)\s*%(?!\s*[\d(])", r"(\1/100)", t)
    return t


def calcular(texto: str) -> float:
    arbol = ast.parse(preparar(texto), mode="eval")
    v = _eval(arbol)
    if isinstance(v, complex) or v != v:
        raise ErrorCalculo("resultado no real")
    return v


def formatear(v: float) -> str:
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15):
        s = f"{int(v):,}".replace(",", ".")
        return s
    s = f"{v:,.10f}".rstrip("0").rstrip(".")
    return s.replace(",", "·").replace(".", ",").replace("·", ".")


def dinero(v: float) -> str:
    """Siempre dos decimales, formato español: 1234.5 → '1.234,50'."""
    return f"{v:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")


def para_copiar(v: float) -> str:
    """Sin separador de miles, con coma decimal (lo que se pega en Excel en español)."""
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15):
        return str(int(v))
    return f"{v:.10f}".rstrip("0").rstrip(".").replace(".", ",")


class Calculadora(Plugin):
    nombre = "calculadora"
    titulo = "Calculadora"
    prefijos = ("=",)
    ejemplo = "2340*1,21 · 15% de 80 · 80 + 21%"

    def buscar(self, consulta, empujar):
        q = consulta.strip()
        if not q or not PARECE.match(q) or not re.search(r"\d", q):
            return []
        if not re.search(r"[+\-*/%^(x×÷]|\b(sqrt|raiz|sin|cos|log|ln|fact)", q, re.I):
            return []  # un número suelto no es una cuenta
        try:
            v = calcular(q)
        except (ErrorCalculo, SyntaxError, ZeroDivisionError, OverflowError, ValueError, TypeError):
            return []
        return [Resultado(formatear(v), f"= {q}  ·  Enter copia el resultado", "=", 3,
                          copiar=para_copiar(v), puntuacion=200, accion_texto="Copiar",
                          completar="=" + para_copiar(v))]
