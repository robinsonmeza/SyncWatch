"""
alertas.py — Umbrales configurables y generación de alertas (P7).

Cada métrica tiene dos umbrales: advertencia y crítico.
Para evitar que una alerta "parpadee" cuando el valor oscila justo en el
límite, se usa HISTÉRESIS: se sube de nivel al alcanzar el umbral, pero solo
se baja cuando el valor cae `histeresis` puntos por debajo.

Ejemplo (cpu, advertencia=75, crítico=90, histéresis=5):
    70 -> normal | 76 -> ADVERTENCIA | 73 -> sigue ADVERTENCIA (73 >= 70)
    69 -> normal | 91 -> CRÍTICO     | 86 -> sigue CRÍTICO (86 >= 85) | 84 -> ADVERTENCIA
"""
from __future__ import annotations

import threading
import time

ORDEN = {"normal": 0, "advertencia": 1, "critico": 2}

UMBRALES_DEFECTO = {
    # métrica      : (nombre legible,          advertencia, crítico, origen)
    "cpu":         ("CPU (real)",              75, 90, "real"),
    "ram":         ("RAM (real)",              80, 92, "real"),
    "disco":       ("Disco (real)",            85, 95, "real"),
    "cpu_sim":     ("CPU simulada",            75, 90, "simulado"),
    "gpu_sim":     ("GPU simulada",            75, 90, "simulado"),
    "ram_sim":     ("RAM simulada",            75, 90, "simulado"),
    "temp_sim":    ("Temperatura simulada °C", 80, 92, "simulado"),
}


class GestorAlertas:
    def __init__(self, bitacora, histeresis: float = 5.0):
        self.bitacora = bitacora
        self.histeresis = histeresis
        self._lock = threading.Lock()
        self.umbrales = {k: {"nombre": v[0], "advertencia": v[1], "critico": v[2], "origen": v[3]}
                         for k, v in UMBRALES_DEFECTO.items()}
        self._nivel = {k: "normal" for k in self.umbrales}
        self._valor = {k: None for k in self.umbrales}

    @staticmethod
    def nivel_para(valor: float, adv: float, crit: float, previo: str, h: float) -> str:
        """Función pura (fácil de probar) que decide el nivel con histéresis."""
        if valor >= crit:
            return "critico"
        if previo == "critico" and valor >= crit - h:
            return "critico"
        if valor >= adv:
            return "advertencia"
        if previo in ("advertencia", "critico") and valor >= adv - h:
            return "advertencia"
        return "normal"

    def evaluar(self, metrica: str, valor) -> str | None:
        """Evalúa un valor. Devuelve el nuevo nivel si hubo cambio, si no None."""
        if valor is None or metrica not in self.umbrales:
            return None
        with self._lock:
            u = self.umbrales[metrica]
            previo = self._nivel[metrica]
            nuevo = self.nivel_para(float(valor), u["advertencia"], u["critico"], previo, self.histeresis)
            self._valor[metrica] = valor
            if nuevo == previo:
                return None
            self._nivel[metrica] = nuevo
        if ORDEN[nuevo] > ORDEN[previo]:
            umbral = u["critico"] if nuevo == "critico" else u["advertencia"]
            self.bitacora.registrar(nuevo, "alerta",
                                    f"{u['nombre']} = {valor:.1f} superó el umbral {nuevo.upper()} ({umbral})")
        else:
            self.bitacora.registrar("info", "alerta",
                                    f"{u['nombre']} bajó a {valor:.1f}: nivel {nuevo.upper()}")
        return nuevo

    def evaluar_muestra_real(self, m: dict):
        for k in ("cpu", "ram", "disco"):
            self.evaluar(k, m.get(k))

    def nivel(self, metrica: str) -> str:
        with self._lock:
            return self._nivel.get(metrica, "normal")

    def reiniciar(self, origen: str):
        """Vuelve a 'normal' las métricas de un origen (p. ej. al iniciar otra simulación)."""
        with self._lock:
            for k, u in self.umbrales.items():
                if u["origen"] == origen:
                    self._nivel[k] = "normal"
                    self._valor[k] = None

    def activas(self) -> list:
        with self._lock:
            return [{"metrica": k, "nombre": self.umbrales[k]["nombre"], "nivel": n,
                     "valor": self._valor[k], "origen": self.umbrales[k]["origen"], "t": time.time()}
                    for k, n in self._nivel.items() if n != "normal"]

    def configurar(self, metrica: str, advertencia: float, critico: float):
        if metrica not in self.umbrales:
            raise KeyError(metrica)
        advertencia, critico = float(advertencia), float(critico)
        if not (0 <= advertencia < critico <= 150):
            raise ValueError("Debe cumplirse 0 <= advertencia < crítico")
        with self._lock:
            self.umbrales[metrica]["advertencia"] = advertencia
            self.umbrales[metrica]["critico"] = critico
        self.bitacora.registrar("info", "alerta",
                                f"Umbrales de {self.umbrales[metrica]['nombre']}: "
                                f"advertencia {advertencia:g}, crítico {critico:g}")

    def listar_umbrales(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self.umbrales.items()}
