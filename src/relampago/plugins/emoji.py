"""Emojis por su nombre en español: ':fuego' · ':risa' · ':ok'. Enter lo pega."""
from __future__ import annotations

from ..nucleo import Plugin, Resultado, normalizar, puntuar

EMOJIS = """
😀 sonrisa feliz contento|😂 risa llorar de risa jaja|🤣 carcajada revolcarse|😊 sonrojado agradable|😍 enamorado corazones ojos
😘 beso|😎 gafas guay chulo|🤔 pensando duda hmm|🙄 ojos en blanco|😴 dormir sueño zzz|😭 llorar triste mucho
😢 lagrima triste|😡 enfadado furioso|🤯 cabeza explota flipando|😱 miedo grito susto|🥳 fiesta cumpleaños
😅 sudor nervios uf|😉 guiño|🙃 al reves ironia|😬 tenso incomodo|🤐 callado secreto|🤮 asco vomitar|🤒 enfermo fiebre
🥶 frio congelado|🥵 calor|😇 angel inocente|🤡 payaso|💀 calavera muerto|👻 fantasma|🤖 robot|👽 alien extraterrestre
👍 ok bien pulgar arriba si|👎 mal pulgar abajo no|👏 aplausos bravo|🙏 gracias por favor rezar|💪 fuerza musculo
👌 perfecto vale ok|✌ paz victoria|🤞 suerte dedos cruzados|👋 hola adios saludo|🤝 trato acuerdo apreton|👀 mirar ojos
🙌 celebrar manos arriba|🫡 saludo militar entendido|🤷 no se encogerse hombros|🤦 facepalm|🧠 cerebro mente
❤ corazon amor rojo|💔 corazon roto|🔥 fuego lit genial|⭐ estrella|✨ brillos magia|⚡ rayo energia relampago
💯 cien perfecto|✅ hecho check correcto verde|❌ cruz error no|⚠ aviso cuidado advertencia|❓ pregunta|❗ exclamacion importante
🎉 fiesta confeti celebracion|🎁 regalo|🎂 tarta cumpleaños|🍕 pizza|🍔 hamburguesa|🍺 cerveza|☕ cafe|🍷 vino
🍎 manzana|🍌 platano|🥑 aguacate|🌮 taco|🍣 sushi|🍫 chocolate|🍿 palomitas|🥂 brindis|🍾 champan
🚀 cohete lanzamiento rapido|💰 dinero bolsa|💸 dinero volando gastar|📈 grafico sube subida|📉 grafico baja bajada|🏦 banco
₿ bitcoin btc|🪙 moneda|💎 diamante manos de diamante|🐂 toro alcista|🐻 oso bajista|🌙 luna to the moon
💻 portatil ordenador|🖥 pantalla ordenador|📱 movil telefono|⌨ teclado|🐍 python serpiente|☕ java|🐛 bug error
📝 nota escribir|📌 chincheta fijar|📎 clip adjunto|📅 calendario fecha|⏰ alarma reloj|⌛ reloj arena esperar|📚 libros estudiar
✏ lapiz|📊 grafico barras|🗂 carpetas|📁 carpeta|🔒 candado cerrado|🔑 llave|🔍 lupa buscar|💡 idea bombilla
🏠 casa|🚗 coche|✈ avion viaje|🏖 playa vacaciones|⛰ montaña|🌍 mundo tierra|☀ sol|🌧 lluvia|❄ nieve|🌈 arcoiris
🐶 perro|🐱 gato|🦊 zorro|🐼 panda|🦁 leon|🐸 rana|🐢 tortuga|🦄 unicornio|🐝 abeja|🦋 mariposa
⚽ futbol balon|🏀 baloncesto|🎮 videojuego mando|🎵 musica nota|🎧 cascos auriculares|🎬 cine pelicula|📷 camara foto
🏆 trofeo copa ganar|🥇 oro primero medalla|🎯 diana objetivo|🧩 puzle pieza|♟ ajedrez|🎲 dado
🇪🇸 españa bandera|🇲🇽 mexico bandera|🇦🇷 argentina bandera|🇺🇸 eeuu estados unidos bandera
""".strip()

LISTA = [(e.split(" ", 1)[0], normalizar(e.split(" ", 1)[1])) for linea in EMOJIS.splitlines()
         for e in linea.split("|") if " " in e]


class Emoji(Plugin):
    nombre = "emoji"
    titulo = "Emojis"
    prefijos = (":",)
    en_general = False
    ejemplo = ":fuego · :risa"

    def buscar(self, consulta, empujar):
        q = normalizar(consulta)
        salida = []
        for emoji, nombres in LISTA:
            s = max(puntuar(q, n) for n in nombres.split()) if q else 10
            if s > 0:
                salida.append(Resultado(f"{emoji}  {nombres.split()[0]}", nombres, emoji, pegar=emoji,
                                        accion_texto="Pegar", puntuacion=s, clave=f"emoji:{emoji}"))
        return sorted(salida, key=lambda r: -r.puntuacion)[:24]
