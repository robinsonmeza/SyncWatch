"""
monitor.py — Lecturas REALES del equipo con psutil (Proyecto 7: SysWatch).

Diseño:
- Un único hilo "muestreador" lee CPU/RAM/disco cada `intervalo` segundos y
  guarda el resultado en una caché protegida por un Lock.
- El resto del programa (API, registrador, alertas) LEE la caché.

¿Por qué así? psutil.cpu_percent(interval=None) calcula el porcentaje respecto
a la llamada ANTERIOR. Si varios hilos lo llamaran a la vez, cada uno "robaría"
el intervalo del otro y los valores saldrían erráticos. Centralizar la lectura
en un solo productor y proteger la caché con un mutex es, en pequeño, el mismo
problema productor-consumidor que estudia el laboratorio (P5).
"""
from __future__ import annotations

import os
import platform
import threading
import time
from collections import deque
from pathlib import Path

import psutil


def es_administrador() -> bool:
    """Indica si el proceso corre con privilegios elevados."""
    try:
        if os.name == "nt":
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def _raiz_disco() -> str:
    """Unidad principal: 'C:\\' en Windows, '/' en Linux/macOS."""
    return Path.home().anchor or "/"


class Monitor:
    def __init__(self, intervalo: float = 1.0, historial: int = 120):
        self.intervalo = intervalo
        self._lock = threading.Lock()
        self._actual: dict = {}
        self._historial: deque = deque(maxlen=historial)
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None
        self._suscriptores = []          # funciones llamadas con cada muestra
        self._disco = _raiz_disco()
        # Primera llamada "en vacío": psutil necesita una referencia previa.
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    # ------------------------------------------------------------------ ciclo
    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, name="muestreador", daemon=True)
        self._hilo.start()

    def detener(self):
        self._detener.set()

    def suscribir(self, funcion):
        """Registra una función que recibe cada muestra nueva (p. ej. alertas)."""
        self._suscriptores.append(funcion)

    def _bucle(self):
        while not self._detener.is_set():
            muestra = self.leer()
            with self._lock:
                self._actual = muestra
                self._historial.append(muestra)
            for f in self._suscriptores:
                try:
                    f(muestra)
                except Exception:
                    pass
            self._detener.wait(self.intervalo)

    # --------------------------------------------------------------- lectura
    def leer(self) -> dict:
        """Lee una muestra directamente del sistema operativo."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        try:
            disco = psutil.disk_usage(self._disco)
            disco_d = {"porcentaje": disco.percent, "usado_gb": round(disco.used / 1e9, 1),
                       "total_gb": round(disco.total / 1e9, 1), "unidad": self._disco}
        except Exception:
            disco_d = {"porcentaje": None, "usado_gb": None, "total_gb": None, "unidad": self._disco}
        return {
            "t": time.time(),
            "cpu": psutil.cpu_percent(interval=None),
            "cpu_nucleos": psutil.cpu_percent(interval=None, percpu=True),
            "ram": mem.percent,
            "ram_usada_gb": round((mem.total - mem.available) / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "swap": swap.percent,
            "disco": disco_d["porcentaje"],
            "disco_info": disco_d,
            "temperatura": self.temperatura(),
        }

    @staticmethod
    def temperatura():
        """Temperatura de CPU si el SO la expone (Linux). En Windows -> None."""
        if not hasattr(psutil, "sensors_temperatures"):
            return None
        try:
            sensores = psutil.sensors_temperatures() or {}
        except Exception:
            return None
        for clave in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
            if sensores.get(clave):
                return round(sensores[clave][0].current, 1)
        for lista in sensores.values():
            if lista:
                return round(lista[0].current, 1)
        return None

    def actual(self) -> dict:
        with self._lock:
            return dict(self._actual) if self._actual else self.leer()

    def historial(self) -> list:
        with self._lock:
            return list(self._historial)

    # -------------------------------------------------------------- procesos
    def procesos(self, limite: int = 10, orden: str = "cpu") -> dict:
        """
        Lista procesos. Algunos campos pueden negarse (AccessDenied) si no se
        ejecuta como administrador; se cuentan como 'restringidos'.
        """
        nucleos = psutil.cpu_count() or 1
        lista, restringidos, total = [], 0, 0
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username", "status"]):
            total += 1
            info = p.info
            if info.get("username") is None or info.get("memory_percent") is None:
                restringidos += 1
            lista.append({
                "pid": info["pid"],
                "nombre": info.get("name") or "¿?",
                # cpu_percent de un proceso puede pasar de 100 % (varios núcleos):
                # se normaliza al total del equipo.
                "cpu": round((info.get("cpu_percent") or 0.0) / nucleos, 1),
                "ram": round(info.get("memory_percent") or 0.0, 1),
                "usuario": info.get("username") or "— (sin permiso)",
                "estado": info.get("status") or "",
            })
        clave = "ram" if orden == "ram" else "cpu"
        lista = [p for p in lista if p["pid"] != 0]   # 'System Idle Process' en Windows
        lista.sort(key=lambda p: p[clave], reverse=True)
        return {"total": total, "restringidos": restringidos, "procesos": lista[:limite]}

    # ---------------------------------------------------------------- sistema
    @staticmethod
    def info_sistema() -> dict:
        temp = Monitor.temperatura()
        return {
            "equipo": platform.node(),
            "so": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "psutil": psutil.__version__,
            "nucleos_logicos": psutil.cpu_count(),
            "nucleos_fisicos": psutil.cpu_count(logical=False),
            "arranque": psutil.boot_time(),
            "administrador": es_administrador(),
            "temperatura_disponible": temp is not None,
        }
