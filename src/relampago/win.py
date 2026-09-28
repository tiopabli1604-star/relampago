"""Integración con Windows vía ctypes (sin dependencias): portapapeles, pegar en la ventana
anterior, atajo de teclado global, notificaciones y esquinas redondeadas."""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

ES_WINDOWS = os.name == "nt"
if ES_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi")

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


# ------------------------------------------------------------------ portapapeles

def _abrir_portapapeles(intentos: int = 10) -> bool:
    for _ in range(intentos):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def leer_portapapeles() -> str | None:
    if not ES_WINDOWS or not _abrir_portapapeles():
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def escribir_portapapeles(texto: str) -> bool:
    if not ES_WINDOWS or not _abrir_portapapeles():
        return False
    try:
        user32.EmptyClipboard()
        datos = ctypes.create_unicode_buffer(texto)
        n = ctypes.sizeof(datos)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, n)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, ctypes.addressof(datos), n)
        kernel32.GlobalUnlock(h)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        user32.CloseClipboard()


def portapapeles_privado() -> bool:
    """True si el contenido actual viene de un gestor de contraseñas (KeePass, 1Password,
    Bitwarden…): ellos marcan el portapapeles para que los historiales NO lo guarden."""
    if not ES_WINDOWS:
        return False
    excluir = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
    if user32.IsClipboardFormatAvailable(excluir):
        return True
    permitir = user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
    if user32.IsClipboardFormatAvailable(permitir) and _abrir_portapapeles():
        try:
            h = user32.GetClipboardData(permitir)
            if h:
                p = kernel32.GlobalLock(h)
                try:
                    return bool(p) and ctypes.c_uint32.from_address(p).value == 0
                finally:
                    kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()
    return False


def secuencia_portapapeles() -> int:
    return user32.GetClipboardSequenceNumber() if ES_WINDOWS else 0


# ------------------------------------------------------------------ ventanas

def ventana_activa() -> int:
    return int(user32.GetForegroundWindow() or 0) if ES_WINDOWS else 0


def titulo_ventana(hwnd: int) -> str:
    if not ES_WINDOWS or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def traer_al_frente(hwnd: int) -> None:
    """SetForegroundWindow con el truco de AttachThreadInput (Windows limita quién puede robar el foco)."""
    if not ES_WINDOWS or not hwnd or not user32.IsWindow(hwnd):
        return
    actual = user32.GetForegroundWindow()
    hilo_actual = user32.GetWindowThreadProcessId(actual, None)
    hilo_propio = kernel32.GetCurrentThreadId()
    unido = hilo_actual and hilo_actual != hilo_propio and user32.AttachThreadInput(hilo_propio, hilo_actual, True)
    try:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if unido:
            user32.AttachThreadInput(hilo_propio, hilo_actual, False)


def pulsar_ctrl_v() -> None:
    VK_CONTROL, VK_V, VK_MENU, KEYUP = 0x11, 0x56, 0x12, 0x0002
    user32.keybd_event(VK_MENU, 0, KEYUP, 0)  # por si Alt sigue "pulsada" del atajo
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def pegar_en(hwnd: int, texto: str) -> None:
    """Copia `texto`, devuelve el foco a la ventana anterior y pulsa Ctrl+V."""
    escribir_portapapeles(texto)
    traer_al_frente(hwnd)
    time.sleep(0.12)
    pulsar_ctrl_v()


def esquinas_redondeadas(hwnd: int) -> None:
    """Esquinas redondeadas y marco oscuro de Windows 11 (en Windows 10 no hace nada)."""
    if not ES_WINDOWS or not hwnd:
        return
    DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 20, 33, 2
    for attr, valor in ((DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND), (DWMWA_USE_IMMERSIVE_DARK_MODE, 1)):
        v = ctypes.c_int(valor)
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))


# ------------------------------------------------------------------ atajo global

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "mayus": 0x4, "win": 0x8}
TECLAS = {"space": 0x20, "espacio": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
          **{f"f{i}": 0x6F + i for i in range(1, 13)}}


def parsear_atajo(texto: str) -> tuple[int, int]:
    """'alt+space' → (MOD_ALT, VK_SPACE)."""
    mods, vk = 0, None
    for parte in texto.lower().replace(" ", "").split("+"):
        if parte in MODS:
            mods |= MODS[parte]
        elif parte in TECLAS:
            vk = TECLAS[parte]
        elif len(parte) == 1 and parte.isalnum():
            vk = ord(parte.upper())
        else:
            raise ValueError(f"Tecla desconocida en el atajo: {parte}")
    if vk is None:
        raise ValueError(f"El atajo '{texto}' no tiene tecla principal")
    return mods, vk


class AtajoGlobal:
    """Registra un atajo del sistema en un hilo con su propio bucle de mensajes."""

    def __init__(self, texto: str, al_pulsar):
        self.texto = texto
        self.mods, self.vk = parsear_atajo(texto)
        self.al_pulsar = al_pulsar
        self.error: str | None = None
        self._listo = threading.Event()
        self._hilo_id = 0

    def iniciar(self) -> bool:
        threading.Thread(target=self._bucle, daemon=True, name="atajo").start()
        self._listo.wait(3)
        return self.error is None

    def _bucle(self):
        MOD_NOREPEAT, WM_HOTKEY = 0x4000, 0x0312
        self._hilo_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self.mods | MOD_NOREPEAT, self.vk):
            self.error = (f"No se pudo registrar {self.texto}: otro programa ya lo usa "
                          "(¿PowerToys Run?). Cambia el atajo en la configuración.")
            self._listo.set()
            return
        self._listo.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    self.al_pulsar()
                except Exception as e:  # noqa: BLE001
                    print("error en el atajo:", e)
        user32.UnregisterHotKey(None, 1)

    def detener(self):
        if self._hilo_id:
            user32.PostThreadMessageW(self._hilo_id, 0x0012, 0, 0)  # WM_QUIT


# ------------------------------------------------------------------ notificaciones

def _xml(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


def notificar(titulo: str, texto: str, sonido: bool = False) -> None:
    """Notificación nativa de Windows (en segundo plano, no bloquea)."""
    if not ES_WINDOWS:
        return
    audio = "" if sonido else "<audio silent='true'/>"
    if sonido:
        audio = "<audio src='ms-winsoundevent:Notification.Looping.Alarm2' loop='false'/>"
    xml = (f"<toast><visual><binding template='ToastGeneric'><text>{_xml(titulo)}</text>"
           f"<text>{_xml(texto)}</text></binding></visual>{audio}</toast>")
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:RLP_XML);"
        "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))"
    )

    def lanzar():
        try:
            subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                           env={**os.environ, "RLP_XML": xml}, capture_output=True, timeout=20,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        except (OSError, subprocess.TimeoutExpired):
            pass

    threading.Thread(target=lanzar, daemon=True).start()


def abrir(objetivo: str) -> None:
    """Abre un archivo, carpeta, URL o URI de Windows con su programa por defecto."""
    if ES_WINDOWS:
        os.startfile(objetivo)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", objetivo])


def mostrar_en_carpeta(ruta: str) -> None:
    if ES_WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])
