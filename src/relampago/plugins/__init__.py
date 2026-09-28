"""Plugins del lanzador. El orden no importa: los resultados se ordenan por puntuación."""
from .apps import Apps
from .archivos import Archivos
from .calculadora import Calculadora
from .conversor import Conversor
from .cripto import Cripto
from .emoji import Emoji
from .ia import IA
from .memoria import Memoria
from .portapapeles import Portapapeles
from .sistema import Sistema
from .snippets import Snippets
from .temporizador import Temporizador
from .web import Web

TODOS = [Apps, Calculadora, Conversor, Cripto, IA, Portapapeles, Archivos, Web, Sistema, Memoria,
         Temporizador, Snippets, Emoji]
