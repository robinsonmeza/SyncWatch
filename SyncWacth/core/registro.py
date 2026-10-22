"""
registro.py — Bitácora de eventos y registro de métricas por intervalos (P7).

- Bitacora: guarda eventos (alertas, bloqueos, anomalías) en memoria y en
  'registros/eventos.log'. Es compartida por varios hilos -> usa un Lock.
- RegistradorMetricas: hilo que cada `intervalo` segundos escribe una fila CSV
  con la última muestra del monitor.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from .rutas import REGISTROS as CARPETA


def _hora(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S")


class Bitacora:
    NIVELES = ("info", "advertencia", "critico")

    def __init__(self, maximo: int = 600, archivo: bool = True):
        self._lock = threading.Lock()
        self._eventos: deque = deque(maxlen=maximo)
        self._id = 0
        self._archivo = None
        if archivo:
            CARPETA.mkdir(parents=True, exist_ok=True)
            self._archivo = CARPETA / "eventos.log"

    def registrar(self, nivel: str, origen: str, mensaje: str) -> dict:
        t = time.time()
        with self._lock:
            self._id += 1
            ev = {"id": self._id, "t": t, "hora": _hora(t), "nivel": nivel,
                  "origen": origen, "mensaje": mensaje}
            self._eventos.append(ev)
            if self._archivo:
                with open(self._archivo, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.fromtimestamp(t):%Y-%m-%d %H:%M:%S} "
                            f"[{nivel.upper():11}] [{origen}] {mensaje}\n")
        return ev

    def listar(self, nivel: str | None = None, origen: str | None = None,
               desde_id: int = 0, limite: int = 200) -> list:
        with self._lock:
            evs = [e for e in self._eventos if e["id"] > desde_id
                   and (not nivel or e["nivel"] == nivel)
                   and (not origen or e["origen"] == origen)]
        return evs[-limite:]

    def csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "fecha_hora", "nivel", "origen", "mensaje"])
        with self._lock:
            for e in self._eventos:
                w.writerow([e["id"], datetime.fromtimestamp(e["t"]).isoformat(timespec="seconds"),
                            e["nivel"], e["origen"], e["mensaje"]])
        return buf.getvalue()


class RegistradorMetricas:
    COLUMNAS = ["fecha_hora", "cpu_%", "ram_%", "ram_usada_gb", "swap_%", "disco_%", "temperatura_c"]

    def __init__(self, monitor, bitacora: Bitacora, intervalo: float = 2.0):
        self.monitor = monitor
        self.bitacora = bitacora
        self.intervalo = intervalo
        self.archivo: Path | None = None
        self.filas = 0
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def activo(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def iniciar(self, intervalo: float | None = None):
        if intervalo:
            self.intervalo = max(0.5, float(intervalo))
        if self.activo:
            return
        CARPETA.mkdir(parents=True, exist_ok=True)
        self.archivo = CARPETA / f"metricas_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with open(self.archivo, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.COLUMNAS)
        self.filas = 0
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, name="registrador", daemon=True)
        self._hilo.start()
        self.bitacora.registrar("info", "registro",
                                f"Registro iniciado cada {self.intervalo:g} s en {self.archivo.name}")

    def detener(self):
        if self.activo:
            self._detener.set()
            self._hilo.join(timeout=2)
            self.bitacora.registrar("info", "registro", f"Registro detenido ({self.filas} filas)")

    def _bucle(self):
        while not self._detener.is_set():
            m = self.monitor.actual()
            fila = [datetime.fromtimestamp(m["t"]).isoformat(timespec="seconds"), m["cpu"], m["ram"],
                    m["ram_usada_gb"], m["swap"], m["disco"],
                    "" if m["temperatura"] is None else m["temperatura"]]
            with self._lock, open(self.archivo, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(fila)
                self.filas += 1
            self._detener.wait(self.intervalo)

    def estado(self) -> dict:
        return {"activo": self.activo, "intervalo": self.intervalo, "filas": self.filas,
                "archivo": self.archivo.name if self.archivo else None, "carpeta": str(CARPETA)}

    def contenido(self) -> str:
        if not self.archivo or not self.archivo.exists():
            return ",".join(self.COLUMNAS) + "\n"
        with self._lock:
            return self.archivo.read_text(encoding="utf-8")
