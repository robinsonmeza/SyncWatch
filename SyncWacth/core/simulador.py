"""
simulador.py — Motor del laboratorio productor-consumidor (P5) con carga
simulada de stress test.

Justificación del enfoque (pedida por la orientación tecnológica de P5):
  * Se usan HILOS REALES (threading) y primitivas REALES (Lock, Semaphore),
    por lo que los bloqueos y la condición de carrera no son una animación:
    ocurren de verdad en el intérprete.
  * El TRABAJO de cada hilo es simulado (time.sleep). Así el experimento es
    seguro (no calienta el equipo), rápido y repetible con una semilla.
  * La "carga" de CPU/GPU/RAM/temperatura del stress test es un MODELO
    numérico derivado de la actividad de los hilos; NO es la carga real del
    equipo (esa la mide monitor.py). En la interfaz se etiqueta "SIMULADO".

Auditoría (regla de conservación):
    producidos = consumidos_únicos + en_búfer   y   duplicados = perdidos = 0
  Cada hilo anota en su PROPIA lista los ítems que insertó o extrajo (listas
  privadas -> sin carrera), de modo que el auditor es confiable aunque el
  búfer no lo sea.
"""
from __future__ import annotations

import random
import threading
import time

from .buffer import BufferInseguro, BufferSincronizado

TICK = 0.25   # periodo del modelo de carga (s)


class _Fin:
    """Condición de parada para los consumidores: stop manual o trabajo terminado."""

    def __init__(self, sim: "Simulacion"):
        self.sim = sim

    def is_set(self) -> bool:
        s = self.sim
        if s._detener.is_set():
            return True
        return s._productores_vivos == 0 and s.buffer.cuenta <= 0


class Trabajador(threading.Thread):
    def __init__(self, sim: "Simulacion", tipo: str, indice: int):
        nombre = f"{'P' if tipo == 'productor' else 'C'}{indice + 1}"
        super().__init__(name=nombre, daemon=True)
        self.sim, self.tipo, self.nombre = sim, tipo, nombre
        self.estado = "listo"
        self.bloqueos = 0
        self.t_bloqueado = 0.0
        self._t_bloqueo_inicio = None
        self.hechos: list = []        # ítems insertados (productor) o extraídos (consumidor)
        self.vacios = 0               # extracciones que devolvieron None (solo inseguro)
        semilla = sim.cfg["semilla"] * 100 + (0 if tipo == "productor" else 50) + indice
        self.rng = random.Random(semilla)

    # -- utilidades -------------------------------------------------------
    def _duracion(self, base: float) -> float:
        lento = self.sim.factor_lentitud if self.tipo == "consumidor" else 1.0
        return base * self.rng.uniform(0.7, 1.3) * lento

    def _al_bloquear(self, motivo: str):
        def f():
            self.estado = motivo
            self.bloqueos += 1
            self._t_bloqueo_inicio = time.perf_counter()
            self.sim._evento_bloqueo(self, motivo)
        return f

    def _fin_bloqueo(self):
        if self._t_bloqueo_inicio is not None:
            self.t_bloqueado += time.perf_counter() - self._t_bloqueo_inicio
            self._t_bloqueo_inicio = None

    def _dormir(self, s: float) -> bool:
        return not self.sim._detener.wait(s)

    # -- ciclo ------------------------------------------------------------
    def run(self):
        try:
            if self.tipo == "productor":
                self._producir()
            else:
                self._consumir()
        finally:
            self._fin_bloqueo()
            self.estado = "terminado"
            if self.tipo == "productor":
                with self.sim._lock_vivos:
                    self.sim._productores_vivos -= 1

    def _producir(self):
        cfg = self.sim.cfg
        for n in range(1, cfg["items_por_productor"] + 1):
            self.estado = "produciendo"
            if not self._dormir(self._duracion(cfg["t_produccion"])):
                return
            item = f"{self.nombre}-{n:03d}"
            self.estado = "insertando"
            ok = self.sim.buffer.insertar(item, al_bloquear=self._al_bloquear("bloqueado_lleno"),
                                          detener=self.sim._detener, quien=self.nombre,
                                          al_hecho=self.hechos.append)
            self._fin_bloqueo()
            if not ok:
                return

    def _consumir(self):
        cfg = self.sim.cfg
        fin = _Fin(self.sim)
        while not fin.is_set():
            self.estado = "esperando"

            def anotar(item):
                if item is None:
                    self.vacios += 1
                else:
                    self.hechos.append(item)

            item = self.sim.buffer.extraer(al_bloquear=self._al_bloquear("bloqueado_vacio"),
                                           detener=fin, quien=self.nombre, al_hecho=anotar)
            self._fin_bloqueo()
            if item is None and fin.is_set():
                return
            self.estado = "consumiendo"
            if item is not None:
                self.sim._consumido(item)
            if not self._dormir(self._duracion(cfg["t_consumo"])):
                return


class Simulacion:
    def __init__(self, cfg: dict, bitacora=None, alertas=None, etiqueta: str = "lab"):
        self.cfg = cfg
        self.bitacora = bitacora
        self.alertas = alertas
        self.etiqueta = etiqueta
        if cfg["sincronizado"]:
            self.buffer = BufferSincronizado(cfg["capacidad"])
        else:
            self.buffer = BufferInseguro(cfg["capacidad"], ventana=cfg["ventana"], semilla=cfg["semilla"])
        self._detener = threading.Event()
        self._lock_vivos = threading.Lock()
        self._productores_vivos = cfg["productores"]
        self.productores = [Trabajador(self, "productor", i) for i in range(cfg["productores"])]
        self.consumidores = [Trabajador(self, "consumidor", i) for i in range(cfg["consumidores"])]
        self.t_inicio = None
        self.t_fin = None
        self.motivo_fin = None
        self.factor_lentitud = 1.0       # >1 durante throttling
        self.throttling = False
        self._t_critico = None
        self.fuga_acumulada = 0.0
        self.carga = {"cpu_sim": 8.0, "gpu_sim": 5.0, "ram_sim": 30.0, "temp_sim": 42.0}
        self.serie: list = []            # historial de la carga simulada y ocupación
        self._ultimo_bloqueo: dict = {}

    # ------------------------------------------------------------- control
    def iniciar(self):
        self.t_inicio = time.perf_counter()
        self._log("info", f"Inicio ({'CON' if self.cfg['sincronizado'] else 'SIN'} sincronización): "
                          f"capacidad {self.cfg['capacidad']}, {self.cfg['productores']} productores, "
                          f"{self.cfg['consumidores']} consumidores, semilla {self.cfg['semilla']}")
        for h in self.productores + self.consumidores:
            h.start()
        threading.Thread(target=self._supervisor, name=f"supervisor-{self.etiqueta}", daemon=True).start()

    def detener(self, motivo: str = "Detenida por el usuario"):
        if not self._detener.is_set():
            self.motivo_fin = self.motivo_fin or motivo
            self._detener.set()

    def esperar(self, timeout: float | None = None):
        limite = None if timeout is None else time.perf_counter() + timeout
        for h in self.productores + self.consumidores:
            restante = None if limite is None else max(0.0, limite - time.perf_counter())
            h.join(restante)

    @property
    def activa(self) -> bool:
        return any(h.is_alive() for h in self.productores + self.consumidores)

    # ------------------------------------------------------------- eventos
    def _log(self, nivel, mensaje):
        if self.bitacora:
            self.bitacora.registrar(nivel, "simulacion", mensaje)

    def _evento_bloqueo(self, hilo: Trabajador, motivo: str):
        # Para no inundar la bitácora: máx. un aviso por hilo cada 2 s.
        ahora = time.perf_counter()
        if ahora - self._ultimo_bloqueo.get(hilo.nombre, -99) < 2:
            return
        self._ultimo_bloqueo[hilo.nombre] = ahora
        if motivo == "bloqueado_lleno":
            self._log("advertencia", f"{hilo.nombre} BLOQUEADO: búfer lleno (espera en P(espacios_libres))")
        else:
            self._log("advertencia", f"{hilo.nombre} BLOQUEADO: búfer vacío (espera en P(items_disponibles))")

    def _consumido(self, item):
        if self.cfg["carga"] == "fuga":
            self.fuga_acumulada += 0.45     # memoria que "no se libera"

    # ------------------------------------------------- modelo de carga simulada
    def _supervisor(self):
        cfg = self.cfg
        rng = random.Random(cfg["semilla"] + 7)
        while True:
            t = time.perf_counter() - self.t_inicio
            vivos = self.activa
            if not vivos:
                break
            if t > cfg["duracion_max"]:
                self.detener(f"Tiempo máximo alcanzado ({cfg['duracion_max']} s)")
            self._actualizar_carga(t, rng)
            self._evaluar_alertas()
            time.sleep(TICK)
        self.t_fin = time.perf_counter()
        if not self.motivo_fin:
            self.motivo_fin = "Completada: todos los ítems fueron procesados"
        self._actualizar_carga(self.t_fin - self.t_inicio, rng, final=True)
        a = self.auditoria()
        nivel = "info" if a["conservacion_ok"] else "critico"
        self._log(nivel, f"Fin — {self.motivo_fin}. Producidos {a['producidos']}, consumidos "
                         f"{a['consumidos']}, en búfer {a['en_buffer']}, perdidos {a['perdidos']}, "
                         f"duplicados {a['duplicados']}. Conservación: {'OK' if a['conservacion_ok'] else 'FALLA'}")

    def _actualizar_carga(self, t: float, rng: random.Random, final: bool = False):
        cfg = self.cfg
        cons = self.consumidores
        prod = self.productores
        util_c = sum(h.estado == "consumiendo" for h in cons) / max(1, len(cons))
        util_p = sum(h.estado == "produciendo" for h in prod) / max(1, len(prod))
        ocup = 100 * max(0, min(self.buffer.capacidad, self.buffer.ocupadas_reales())) / self.buffer.capacidad
        ruido = lambda a: rng.uniform(-a, a)

        if final:
            obj_cpu, obj_gpu = 6, 4
        elif cfg["carga"] == "stress":
            intensidad = min(1.0, t / 15.0)                    # rampa de 15 s
            obj_cpu = 20 + 82 * intensidad * (0.65 + 0.35 * util_c)
            obj_gpu = 10 + 88 * intensidad
            if self.throttling:                               # el "sistema" baja la frecuencia de la CPU,
                obj_cpu = min(obj_cpu, 70)                     # pero la GPU sigue al máximo
        else:
            obj_cpu = 10 + 40 * util_c + 10 * util_p
            obj_gpu = 5 + 6 * util_c

        c = self.carga
        c["cpu_sim"] += 0.35 * (obj_cpu - c["cpu_sim"]) + ruido(2)
        c["gpu_sim"] += 0.30 * (obj_gpu - c["gpu_sim"]) + ruido(1.5)
        # La temperatura sigue a la carga con retraso (inercia térmica)
        obj_temp = 36 + 0.58 * max(c["cpu_sim"], c["gpu_sim"])
        c["temp_sim"] += 0.10 * (obj_temp - c["temp_sim"]) + ruido(0.4)
        c["ram_sim"] = 28 + 0.12 * ocup + self.fuga_acumulada + ruido(0.5)
        for k in c:
            c[k] = round(max(0.0, min(100.0 if k != "temp_sim" else 110.0, c[k])), 1)
        self.serie.append({"t": round(t, 2), **c, "buffer": round(ocup, 1)})
        if len(self.serie) > 400:
            del self.serie[0]

    def _evaluar_alertas(self):
        if not self.alertas:
            return
        c = self.carga
        for k in ("cpu_sim", "gpu_sim", "ram_sim", "temp_sim"):
            self.alertas.evaluar(k, c[k])

        # Reacciones automáticas (el "sistema operativo simulado" se defiende)
        temp_crit = self.alertas.nivel("temp_sim") == "critico" or self.alertas.nivel("cpu_sim") == "critico"
        if self.cfg["carga"] == "stress":
            if temp_crit and not self.throttling:
                self.throttling = True
                self.factor_lentitud = 2.0
                self._log("critico", "THROTTLING térmico (simulado): la CPU baja al 70 % y los workers se ralentizan al 50 %")
            if temp_crit:
                self._t_critico = self._t_critico or time.perf_counter()
                if time.perf_counter() - self._t_critico > 6:
                    self._log("critico", "AUTOPROTECCIÓN: el throttling no bastó (la GPU sigue al máximo); nivel crítico sostenido 6 s, se detiene el stress test")
                    self.detener("Autoprotección por temperatura/CPU crítica (simulado)")
            else:
                self._t_critico = None
        if self.cfg["carga"] == "fuga" and self.alertas.nivel("ram_sim") == "critico":
            self._log("critico", "MEMORIA AGOTADA (simulado): se detiene la simulación")
            self.detener("RAM simulada en nivel crítico por fuga de memoria")

    # ------------------------------------------------------------ auditoría
    def auditoria(self) -> dict:
        def calcular():
            producidos = [i for p in self.productores for i in list(p.hechos)]
            consumidos = [i for c in self.consumidores for i in list(c.hechos)]
            en_buffer = [i for i in self.buffer.casillas() if i is not None]
            return producidos, consumidos, en_buffer

        if self.buffer.sincronizado:
            with self.buffer.mutex:              # foto consistente del estado
                producidos, consumidos, en_buffer = calcular()
        else:
            producidos, consumidos, en_buffer = calcular()

        set_c = set(consumidos)
        set_b = set(en_buffer)
        perdidos = sorted(set(producidos) - set_c - set_b)
        duplicados_n = len(consumidos) - len(set_c) + len(set_c & set_b)
        vistos, duplicados = set(), []
        for i in consumidos:
            if i in vistos:
                duplicados.append(i)
            vistos.add(i)
        vacios = sum(c.vacios for c in self.consumidores)
        ok = (len(producidos) == len(set_c) + len(set_b) and not perdidos and duplicados_n == 0
              and vacios == 0 and self.buffer.cuenta == len(en_buffer))
        return {
            "producidos": len(producidos),
            "consumidos": len(consumidos),
            "consumidos_unicos": len(set_c),
            "en_buffer": len(en_buffer),
            "cuenta_buffer": self.buffer.cuenta,
            "perdidos": len(perdidos),
            "duplicados": duplicados_n,
            "lecturas_vacias": vacios,
            "sobrescrituras": self.buffer.sobrescrituras,
            "desbordes": self.buffer.desbordes,
            "ejemplo_perdidos": perdidos[:5],
            "ejemplo_duplicados": duplicados[:5],
            "conservacion_ok": ok,
        }

    # -------------------------------------------------------------- estado
    def explicacion(self, hilos: list, a: dict) -> str:
        b = self.buffer
        lleno = sum(h["estado"] == "bloqueado_lleno" for h in hilos)
        vacio = sum(h["estado"] == "bloqueado_vacio" for h in hilos)
        if not self.activa and self.t_inicio:
            if a["conservacion_ok"]:
                return "Simulación terminada. La regla de conservación se cumple: ningún ítem se perdió ni se duplicó."
            return ("Simulación terminada con CONDICIÓN DE CARRERA: hubo hilos que leyeron/escribieron los mismos "
                    "índices a la vez porque nada impedía que se intercalaran.")
        if not b.sincronizado:
            if a["perdidos"] or a["duplicados"] or a["lecturas_vacias"]:
                return ("Sin mutex, dos hilos pueden leer el mismo índice antes de que el otro lo actualice: "
                        f"ya hay {a['perdidos']} ítems perdidos y {a['duplicados']} duplicados.")
            return "Sin sincronización: los hilos acceden al búfer al mismo tiempo. Observa los contadores de anomalías."
        if self.throttling:
            return "Throttling activo: la temperatura simulada superó el umbral crítico y los workers se ralentizan."
        if lleno:
            return (f"Búfer LLENO: {lleno} productor(es) bloqueado(s). El semáforo espacios_libres vale 0, "
                    "así que P(espacios_libres) los duerme hasta que un consumidor libere una casilla.")
        if vacio:
            return (f"Búfer VACÍO: {vacio} consumidor(es) bloqueado(s). El semáforo items_disponibles vale 0, "
                    "así que esperan a que un productor inserte un ítem.")
        return "Flujo normal: el mutex garantiza que solo un hilo modifique el búfer a la vez."

    def estado(self) -> dict:
        hilos = [{"nombre": h.nombre, "tipo": h.tipo, "estado": h.estado, "hechos": len(h.hechos),
                  "bloqueos": h.bloqueos, "t_bloqueado": round(h.t_bloqueado, 2)}
                 for h in self.productores + self.consumidores]
        a = self.auditoria()
        fin = self.t_fin or time.perf_counter()
        return {
            "config": self.cfg,
            "activa": self.activa,
            "transcurrido": round(fin - self.t_inicio, 1) if self.t_inicio else 0,
            "motivo_fin": self.motivo_fin if not self.activa else None,
            "buffer": {"capacidad": self.buffer.capacidad, "casillas": self.buffer.casillas(),
                       "entrada": self.buffer.entrada, "salida": self.buffer.salida,
                       "cuenta": self.buffer.cuenta, "ocupadas": self.buffer.ocupadas_reales(),
                       "sincronizado": self.buffer.sincronizado, **self.buffer.semaforos()},
            "hilos": hilos,
            "bloqueos_total": sum(h["bloqueos"] for h in hilos),
            "auditoria": a,
            "carga": dict(self.carga),
            "throttling": self.throttling,
            "serie": self.serie[-160:],
            "explicacion": self.explicacion(hilos, a),
        }


def comparar(cfg_base: dict, timeout: float = 60) -> dict:
    """Ejecuta la MISMA configuración con y sin sincronización, en paralelo."""
    resultados = {}
    sims = {}
    for modo in ("sin", "con"):
        cfg = dict(cfg_base, sincronizado=(modo == "con"), carga="normal")
        sims[modo] = Simulacion(cfg, etiqueta=f"cmp-{modo}")
    for s in sims.values():
        s.iniciar()
    for s in sims.values():
        s.esperar(timeout)
        if s.activa:
            s.detener("Tiempo de comparación agotado")
            s.esperar(3)
    for modo, s in sims.items():
        a = s.auditoria()
        resultados[modo] = {**a, "tiempo": round((s.t_fin or time.perf_counter()) - s.t_inicio, 2),
                            "bloqueos": sum(h.bloqueos for h in s.productores + s.consumidores)}
    return {"config": dict(cfg_base), "sin": resultados["sin"], "con": resultados["con"]}
