import time

import pytest

from relampago.nucleo import Contexto, Motor, Plugin, Resultado, Uso, normalizar, puntuar
from relampago.plugins import calculadora as calc
from relampago.plugins import conversor as conv
from relampago.plugins import temporizador as temp
from relampago.plugins.apps import iniciales
from relampago.plugins.cripto import Cripto
from relampago.plugins.emoji import Emoji
from relampago.plugins.snippets import Snippets
from relampago.plugins.web import Web
from relampago import win


@pytest.fixture
def ctx(tmp_path):
    return Contexto({"snippets": {"correo": "yo@ejemplo.com"}}, Uso(tmp_path / "uso.json"))


# ------------------------------------------------------------------ búsqueda

def test_normalizar_quita_tildes():
    assert normalizar("Cámara ÁÉÍÓÚ Ñ") == "camara aeiou n"


@pytest.mark.parametrize("q,texto,minimo", [
    ("chr", "google chrome", 80), ("vsc", "visual studio code", 75), ("note", "notion", 0),
    ("code", "visual studio code", 80), ("vscode", "visual studio code", 10),
])
def test_puntuar(q, texto, minimo):
    s = puntuar(q, texto)
    assert (s >= minimo) if minimo else s == 0


def test_subsecuencia_solo_por_palabras():
    assert puntuar("btc", normalizar("Subtítulos en directo")) == 0
    assert puntuar("btc", normalizar("Comprobar Actualizaciones")) == 0
    assert puntuar("vscode", "visual studio code") > 0
    assert puntuar("gchr", "google chrome") > 0


def test_puntuar_prefiere_prefijo():
    assert puntuar("no", "notion") > puntuar("no", "piano")


def test_uso_aprende(tmp_path):
    u = Uso(tmp_path / "u.json")
    assert u.extra("app:x") == 0
    for _ in range(4):
        u.registrar("app:x")
    assert u.extra("app:x") > 20
    assert Uso(tmp_path / "u.json").extra("app:x") > 20   # persistido


def test_motor_prefijos_y_orden(ctx):
    class A(Plugin):
        nombre = "a"
        def buscar(self, c, e):
            return [Resultado("a-bajo", puntuacion=10), Resultado("a-alto", puntuacion=90)]

    class B(Plugin):
        nombre = "b"
        prefijos = ("cb ",)
        en_general = False
        def buscar(self, c, e):
            return [Resultado(f"b:{c}", puntuacion=1)]

    m = Motor(ctx, [A, B])
    _, r = m.buscar("hola")
    assert [x["titulo"] for x in r] == ["a-alto", "a-bajo"]
    assert [x["titulo"] for x in m.buscar("cb factura")[1]] == ["b:factura"]
    assert [x["titulo"] for x in m.buscar("cb")[1]] == ["b:"]
    assert [x["titulo"] for x in m.buscar("cbx")[1]] == ["a-alto", "a-bajo"]


def test_motor_resultados_tardios_y_obsoletos(ctx):
    empujes = []

    class Lento(Plugin):
        nombre = "lento"
        def buscar(self, c, empujar):
            self.empujar = empujar
            return [Resultado("cargando…")]

    m = Motor(ctx, [Lento])
    m.al_actualizar = lambda cid, r: empujes.append((cid, [x["titulo"] for x in r]))
    cid, _ = m.buscar("x")
    viejo = m.plugins[0].empujar
    viejo([Resultado("listo")])
    assert empujes == [(cid, ["listo"])]
    m.buscar("y")                 # el usuario siguió escribiendo
    viejo([Resultado("tarde")])   # la respuesta vieja ya no debe pintarse
    assert len(empujes) == 1


def test_ejecutar_registra_uso(ctx):
    llamado = []

    class A(Plugin):
        nombre = "a"
        def buscar(self, c, e):
            return [Resultado("x", accion=lambda: llamado.append(1), clave="k")]

    m = Motor(ctx, [A])
    m.buscar("x")
    assert m.ejecutar(0)["ocultar"] is True
    assert llamado == [1] and ctx.uso.extra("k") > 0


# ------------------------------------------------------------------ calculadora

@pytest.mark.parametrize("expr,esperado", [
    ("2+2", 4), ("2340*1,21", 2831.4), ("15% de 80", 12), ("80 + 21%", 96.8), ("100 - 15%", 85),
    ("2^10", 1024), ("sqrt(16)", 4), ("(1+2)*3", 9), ("3x4", 12), ("10/4", 2.5), ("1,234,567*2", 2469134),
])
def test_calcular(expr, esperado):
    assert calc.calcular(expr) == pytest.approx(esperado)


@pytest.mark.parametrize("peligroso", ["__import__('os')", "open('x')", "().__class__", "9**9**9", "a+b"])
def test_calculadora_no_ejecuta_codigo(peligroso):
    with pytest.raises((calc.ErrorCalculo, SyntaxError, ValueError)):
        calc.calcular(peligroso)


def test_formato_es():
    assert calc.formatear(2831.4) == "2.831,4"
    assert calc.formatear(1234567) == "1.234.567"
    assert calc.para_copiar(2831.4) == "2831,4"
    assert calc.dinero(87.7) == "87,70"
    assert calc.dinero(1234567.891) == "1.234.567,89"


def test_plugin_calculadora_ignora_texto(ctx):
    p = calc.Calculadora(ctx)
    assert p.buscar("chrome", None) == []
    assert p.buscar("2024", None) == []            # número suelto no es cuenta
    assert p.buscar("2+2", None)[0].titulo == "4"


# ------------------------------------------------------------------ conversor

@pytest.mark.parametrize("texto,esperado", [
    ("10 km a millas", 6.2137), ("30 c a f", 86), ("5 gb en mb", 5120), ("1 milla a km", 1.609344),
    ("100 f a c", 37.7778), ("2 horas a minutos", 120), ("1,5 kg a libras", 3.3069),
])
def test_convertir(texto, esperado):
    assert conv.convertir(texto)[3] == pytest.approx(esperado, rel=1e-3)


def test_convertir_magnitudes_incompatibles():
    assert conv.convertir("10 km a kg") is None


# ------------------------------------------------------------------ temporizador

@pytest.mark.parametrize("texto,seg,etiqueta", [
    ("25m", 1500, ""), ("1h30m sacar la ropa", 5400, "sacar la ropa"), ("1h 30m", 5400, ""),
    ("90s", 90, ""), ("5", 300, ""), ("10 pasta", 600, "pasta"), ("25 min pomodoro", 1500, "pomodoro"),
])
def test_parsear_duraciones(texto, seg, etiqueta):
    assert temp.parsear(texto) == (seg, etiqueta)


def test_parsear_hora():
    s, et = temp.parsear("23:59 dormir")
    assert 0 < s <= 86400 and et == "dormir"
    assert temp.parsear("25:00") is None
    assert temp.parsear("hola") is None


def test_temporizador_crea_y_cancela(ctx, monkeypatch):
    avisos = []
    monkeypatch.setattr(win, "notificar", lambda t, m, sonido=False: avisos.append(t))
    p = temp.Temporizador(ctx)
    p.crear(0.2, "té")
    assert len(p.activos) == 1
    time.sleep(0.5)
    assert avisos == ["⏰ té"] and not p.activos
    p.crear(60, "")
    p.cancelar(next(iter(p.activos)))
    assert not p.activos


# ------------------------------------------------------------------ otros plugins

def test_web_atajos(ctx):
    r = Web(ctx).buscar("yt lofi hip hop", None)[0]
    assert "youtube.com" in r.subtitulo and "lofi+hip+hop" in r.subtitulo
    assert "https://github.com" in Web(ctx).buscar("github.com", None)[0].subtitulo


def test_snippets_propios_y_dinamicos(ctx):
    res = Snippets(ctx).buscar("corr", None)
    assert res[0].pegar == "yo@ejemplo.com"
    fecha = [r for r in Snippets(ctx).buscar("fecha", None) if r.titulo.startswith(";fecha")][0]
    assert fecha.pegar.count("/") == 2


def test_emoji_por_nombre(ctx):
    assert Emoji(ctx).buscar("fuego", None)[0].pegar == "🔥"


def test_cripto_solo_reacciona_a_monedas(ctx):
    assert Cripto(ctx).buscar("chrome", None) == []
    assert Cripto(ctx).buscar("hola mundo", None) == []


def test_iniciales_apps():
    assert iniciales("Visual Studio Code") == "VS"
    assert iniciales("Notion") == "No"


def test_atajo():
    assert win.parsear_atajo("alt+space") == (0x1, 0x20)
    assert win.parsear_atajo("ctrl+shift+k") == (0x2 | 0x4, ord("K"))
    with pytest.raises(ValueError):
        win.parsear_atajo("alt+patata")


@pytest.mark.skipif(not win.ES_WINDOWS, reason="solo Windows")
def test_portapapeles_ida_y_vuelta():
    previo = win.leer_portapapeles()
    try:
        assert win.escribir_portapapeles("relámpago ⚡ prueba")
        assert win.leer_portapapeles() == "relámpago ⚡ prueba"
    finally:
        if previo is not None:
            win.escribir_portapapeles(previo)
