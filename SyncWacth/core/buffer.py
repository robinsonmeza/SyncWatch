"""
buffer.py — Búfer circular compartido (Proyecto 5: SyncLab).

Dos implementaciones con la MISMA interfaz:

1. BufferSincronizado  (solución clásica de Dijkstra)
   - mutex            : exclusión mutua. Solo un hilo a la vez modifica
                        los índices y la cuenta (sección crítica).
   - espacios_libres  : semáforo contador, empieza en `capacidad`.
                        El productor hace acquire() antes de insertar;
                        si vale 0 (búfer LLENO) el productor se BLOQUEA.
   - items_disponibles: semáforo contador, empieza en 0.
                        El consumidor hace acquire() antes de extraer;
                        si vale 0 (búfer VACÍO) el consumidor se BLOQUEA.

       productor:  P(espacios) -> P(mutex) -> insertar -> V(mutex) -> V(items)
       consumidor: P(items)    -> P(mutex) -> extraer  -> V(mutex) -> V(espacios)

2. BufferInseguro  (sin sincronización, para el experimento)
   - Comprueba "¿hay espacio?" con una espera activa y luego escribe,
     pero entre leer y escribir los índices hay una ventana en la que otro
     hilo puede intercalarse (se fuerza con un pequeño sleep que simula un
     cambio de contexto). Resultado: condición de carrera -> ítems
     sobrescritos (perdidos), ítems leídos dos veces (duplicados), lecturas
     de casillas vacías y una `cuenta` que no coincide con la realidad.
"""
from __future__ import annotations

import random
import threading
import time


def _nada():
    pass


class _BaseBuffer:
    sincronizado = False

    def __init__(self, capacidad: int):
        if capacidad < 1:
            raise ValueError("La capacidad debe ser >= 1")
        self.capacidad = capacidad
        self._casillas = [None] * capacidad
        self.entrada = 0          # siguiente posición para insertar
        self.salida = 0           # siguiente posición para extraer
        self.cuenta = 0           # cuántos ítems CREE el búfer que tiene
        # Contadores de diagnóstico (no forman parte del algoritmo)
        self.desbordes = 0        # veces que cuenta > capacidad o < 0
        self.lecturas_vacias = 0  # extracciones que encontraron la casilla vacía
        self.sobrescrituras = 0   # inserciones que pisaron un ítem sin consumir

    def casillas(self) -> list:
        return list(self._casillas)

    def ocupadas_reales(self) -> int:
        return sum(1 for c in self._casillas if c is not None)


class BufferSincronizado(_BaseBuffer):
    sincronizado = True

    def __init__(self, capacidad: int):
        super().__init__(capacidad)
        self.mutex = threading.Lock()
        self.espacios_libres = threading.Semaphore(capacidad)
        self.items_disponibles = threading.Semaphore(0)
        # Espejos legibles de los semáforos (threading.Semaphore no expone su valor)
        self._sem_espacios = capacidad
        self._sem_items = 0
        self._mutex_duenio: str | None = None

    @staticmethod
    def _esperar(sem: threading.Semaphore, al_bloquear, detener: threading.Event | None) -> bool:
        """acquire() que avisa cuando el hilo se bloquea y puede cancelarse."""
        if sem.acquire(blocking=False):
            return True
        al_bloquear()                              # el hilo queda BLOQUEADO
        while True:
            if sem.acquire(timeout=0.05):
                return True
            if detener is not None and detener.is_set():
                return False

    def insertar(self, item, al_bloquear=_nada, detener=None, quien: str = "", al_hecho=None) -> bool:
        if not self._esperar(self.espacios_libres, al_bloquear, detener):   # P(espacios)
            return False
        with self.mutex:                                                    # P(mutex)
            self._mutex_duenio = quien
            self._sem_espacios -= 1
            if self._casillas[self.entrada] is not None:
                self.sobrescrituras += 1           # nunca debería ocurrir
            self._casillas[self.entrada] = item
            self.entrada = (self.entrada + 1) % self.capacidad
            self.cuenta += 1
            if self.cuenta > self.capacidad:
                self.desbordes += 1
            self._sem_items += 1
            if al_hecho:
                al_hecho(item)                     # auditoría dentro de la sección crítica
            self._mutex_duenio = None
        self.items_disponibles.release()                                   # V(items)
        return True

    def extraer(self, al_bloquear=_nada, detener=None, quien: str = "", al_hecho=None):
        if not self._esperar(self.items_disponibles, al_bloquear, detener):  # P(items)
            return None
        with self.mutex:                                                    # P(mutex)
            self._mutex_duenio = quien
            self._sem_items -= 1
            item = self._casillas[self.salida]
            if item is None:
                self.lecturas_vacias += 1          # nunca debería ocurrir
            self._casillas[self.salida] = None
            self.salida = (self.salida + 1) % self.capacidad
            self.cuenta -= 1
            if self.cuenta < 0:
                self.desbordes += 1
            self._sem_espacios += 1
            if al_hecho:
                al_hecho(item)
            self._mutex_duenio = None
        self.espacios_libres.release()                                     # V(espacios)
        return item

    def semaforos(self) -> dict:
        return {"espacios_libres": self._sem_espacios, "items_disponibles": self._sem_items,
                "mutex": "ocupado" if self._mutex_duenio else "libre",
                "mutex_duenio": self._mutex_duenio}


class BufferInseguro(_BaseBuffer):
    sincronizado = False

    def __init__(self, capacidad: int, ventana: float = 0.002, semilla: int | None = None):
        super().__init__(capacidad)
        self.ventana = ventana                     # duración máx. del "cambio de contexto"
        self._rng = random.Random(semilla)

    def _cambio_de_contexto(self):
        # Cede la CPU en el peor momento posible: entre leer y escribir estado compartido.
        time.sleep(self._rng.uniform(0, self.ventana))

    def insertar(self, item, al_bloquear=_nada, detener=None, quien: str = "", al_hecho=None) -> bool:
        avisado = False
        while self.cuenta >= self.capacidad:       # espera activa SIN exclusión mutua
            if not avisado:
                al_bloquear(); avisado = True
            if detener is not None and detener.is_set():
                return False
            time.sleep(0.005)
        pos = self.entrada                         # 1) leer índice compartido
        self._cambio_de_contexto()                 #    <- otro productor puede leer el mismo
        if self._casillas[pos] is not None:
            self.sobrescrituras += 1               # se pisa un ítem que nadie consumió
        self._casillas[pos] = item                 # 2) escribir
        self.entrada = (pos + 1) % self.capacidad  # 3) avanzar índice
        c = self.cuenta                            # read-modify-write NO atómico
        self._cambio_de_contexto()
        self.cuenta = c + 1
        if self.cuenta > self.capacidad or self.cuenta < 0:
            self.desbordes += 1
        if al_hecho:
            al_hecho(item)
        return True

    def extraer(self, al_bloquear=_nada, detener=None, quien: str = "", al_hecho=None):
        avisado = False
        while self.cuenta <= 0:
            if not avisado:
                al_bloquear(); avisado = True
            if detener is not None and detener.is_set():
                return None
            time.sleep(0.005)
        pos = self.salida                          # 1) leer índice compartido
        item = self._casillas[pos]                 # 2) leer el ítem
        if item is None:
            self.lecturas_vacias += 1
        self._cambio_de_contexto()                 # <- otro consumidor lee la MISMA casilla (duplicado)
        self._casillas[pos] = None                 # 3) liberar casilla
        self.salida = (pos + 1) % self.capacidad
        c = self.cuenta
        self._cambio_de_contexto()
        self.cuenta = c - 1
        if self.cuenta > self.capacidad or self.cuenta < 0:
            self.desbordes += 1
        if al_hecho:
            al_hecho(item)
        return item

    def semaforos(self) -> dict:
        return {"espacios_libres": None, "items_disponibles": None, "mutex": "sin mutex",
                "mutex_duenio": None}
