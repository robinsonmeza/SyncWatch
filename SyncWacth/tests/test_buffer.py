"""Pruebas del búfer: límites, bloqueo con semáforos y condición de carrera."""
import threading
import time

import pytest

from core.buffer import BufferInseguro, BufferSincronizado


def test_fifo_un_hilo():
    b = BufferSincronizado(3)
    for x in ("a", "b", "c"):
        assert b.insertar(x)
    assert [b.extraer() for _ in range(3)] == ["a", "b", "c"]
    assert b.cuenta == 0 and b.ocupadas_reales() == 0


def test_productor_se_bloquea_con_buffer_lleno():
    """Caso de prueba: capacidad 2, se insertan 2 ítems; el 3.º debe bloquearse en P(espacios_libres)."""
    b = BufferSincronizado(2)
    assert b.insertar(1) and b.insertar(2)
    assert b.semaforos()["espacios_libres"] == 0
    bloqueado = threading.Event()
    detener = threading.Event()
    threading.Timer(0.3, detener.set).start()
    t0 = time.perf_counter()
    ok = b.insertar(3, al_bloquear=bloqueado.set, detener=detener)
    assert bloqueado.is_set() and not ok
    assert time.perf_counter() - t0 >= 0.25          # realmente esperó
    assert b.cuenta == 2                              # no se desbordó


def test_consumidor_se_bloquea_con_buffer_vacio_y_despierta():
    b = BufferSincronizado(2)
    bloqueado = threading.Event()
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.append(b.extraer(al_bloquear=bloqueado.set)))
    hilo.start()
    assert bloqueado.wait(1)                          # está dormido en P(items_disponibles)
    b.insertar("x")                                   # V(items_disponibles) lo despierta
    hilo.join(2)
    assert resultado == ["x"]


@pytest.mark.parametrize("capacidad", [1, 3, 8])
def test_sincronizado_nunca_desborda(capacidad):
    b = BufferSincronizado(capacidad)
    N, P, C = 200, 4, 4
    consumidos = []
    lock = threading.Lock()

    def prod(i):
        for n in range(N):
            b.insertar((i, n))
            assert 0 <= b.cuenta <= capacidad

    def cons():
        for _ in range(N):
            x = b.extraer()
            with lock:
                consumidos.append(x)

    hilos = [threading.Thread(target=prod, args=(i,)) for i in range(P)] + \
            [threading.Thread(target=cons) for _ in range(C)]
    for h in hilos: h.start()
    for h in hilos: h.join(20)
    assert len(consumidos) == N * P == len(set(consumidos))   # ni perdidos ni duplicados
    assert b.desbordes == b.lecturas_vacias == b.sobrescrituras == 0
    assert b.cuenta == 0


def test_inseguro_produce_condicion_de_carrera():
    b = BufferInseguro(8, ventana=0.003, semilla=1)
    N, P, C = 40, 3, 3
    consumidos = []
    fin = threading.Event()

    def prod(i):
        for n in range(N):
            b.insertar((i, n), detener=fin)

    def cons():
        while not fin.is_set():
            x = b.extraer(detener=fin)
            if x is not None:
                consumidos.append(x)

    ps = [threading.Thread(target=prod, args=(i,)) for i in range(P)]
    cs = [threading.Thread(target=cons) for _ in range(C)]
    for h in ps + cs: h.start()
    for h in ps: h.join(20)
    time.sleep(0.5); fin.set()
    for h in cs: h.join(5)
    anomalias = b.sobrescrituras + b.lecturas_vacias + (len(consumidos) - len(set(consumidos)))
    assert anomalias > 0, "sin sincronización deberían aparecer anomalías"
