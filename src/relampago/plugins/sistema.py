"""Controles del sistema y accesos a Configuración: 'bloquear' · 'suspender' · 'apagar' · 'wifi' · 'bluetooth'
Lo peligroso (apagar, reiniciar, cerrar sesión) pide un segundo Enter."""
from __future__ import annotations

import ctypes
import os
import subprocess

from ..nucleo import Plugin, Resultado, normalizar, puntuar
from .. import win


def _cmd(*args):
    return lambda: subprocess.Popen(list(args), creationflags=0x08000000)


def _bloquear():
    ctypes.windll.user32.LockWorkStation()


def _suspender():
    ctypes.windll.powrprof.SetSuspendState(False, True, False)


def _ms(uri):
    return lambda: win.abrir(uri)


# (título, palabras clave, icono, acción, confirmación)
COMANDOS = [
    ("Bloquear el equipo", "bloquear lock pantalla", "🔒", _bloquear, ""),
    ("Suspender", "suspender dormir sleep", "🌙", _suspender, ""),
    ("Apagar", "apagar shutdown", "⏻", _cmd("shutdown", "/s", "/t", "0"), "¿Apagar el equipo? Enter otra vez"),
    ("Reiniciar", "reiniciar restart reboot", "↻", _cmd("shutdown", "/r", "/t", "0"),
     "¿Reiniciar el equipo? Enter otra vez"),
    ("Cerrar sesión", "cerrar sesion logout logoff", "⎋", _cmd("shutdown", "/l"), "¿Cerrar sesión? Enter otra vez"),
    ("Wi-Fi", "wifi red internet", "📶", _ms("ms-settings:network-wifi"), ""),
    ("Bluetooth", "bluetooth auriculares", "ᛒ", _ms("ms-settings:bluetooth"), ""),
    ("Pantalla", "pantalla brillo resolucion monitor", "🖥", _ms("ms-settings:display"), ""),
    ("Sonido", "sonido audio volumen altavoz microfono", "🔊", _ms("ms-settings:sound"), ""),
    ("Windows Update", "actualizaciones update windows", "⟳", _ms("ms-settings:windowsupdate"), ""),
    ("Aplicaciones instaladas", "aplicaciones programas desinstalar", "▦", _ms("ms-settings:appsfeatures"), ""),
    ("Aplicaciones de inicio", "inicio arranque startup", "🚀", _ms("ms-settings:startupapps"), ""),
    ("Almacenamiento", "almacenamiento disco espacio", "💽", _ms("ms-settings:storagesense"), ""),
    ("Batería y energía", "bateria energia power", "🔋", _ms("ms-settings:powersleep"), ""),
    ("Impresoras", "impresora imprimir printer", "🖨", _ms("ms-settings:printers"), ""),
    ("Fondo de pantalla", "fondo personalizar wallpaper", "🎨", _ms("ms-settings:personalization-background"), ""),
    ("Administrador de tareas", "administrador tareas task manager procesos", "📊", _cmd("taskmgr"), ""),
    ("Panel de control", "panel control", "🛠", _cmd("control"), ""),
    ("Papelera de reciclaje", "papelera reciclaje", "🗑", _ms("shell:RecycleBinFolder"), ""),
    ("Descargas", "descargas downloads", "⬇", lambda: win.abrir(os.path.expanduser("~/Downloads")), ""),
    ("Recorte de pantalla", "captura recorte screenshot", "✂", _ms("ms-screenclip:"), ""),
    ("Terminal", "terminal consola powershell cmd", ">_", _cmd("wt"), ""),
]


class Sistema(Plugin):
    nombre = "sistema"
    titulo = "Sistema"
    ejemplo = "bloquear · wifi · apagar"

    def buscar(self, consulta, empujar):
        q = normalizar(consulta)
        if len(q) < 2:
            return []
        salida = []
        for titulo, claves, icono, accion, confirmar in COMANDOS:
            s = max(puntuar(q, normalizar(titulo)), *(puntuar(q, k) for k in claves.split()))
            if s >= 60:
                salida.append(Resultado(titulo, "Sistema", icono, 4, accion=accion, confirmar=confirmar,
                                        puntuacion=s, clave=f"sis:{titulo}", accion_texto="Ejecutar"))
        return salida
