"""Pruebas de umbrales/alertas y del monitor real."""
import pytest

from core.alertas import GestorAlertas
from core.monitor import Monitor
from core.registro import Bitacora

N = GestorAlertas.nivel_para


@pytest.mark.parametrize("valor,previo,esperado", [
    (70, "normal", "normal"),
    (76, "normal", "advertencia"),
    (73, "advertencia", "advertencia"),   # histéresis: no baja hasta < 70
    (69, "advertencia", "normal"),
    (91, "normal", "critico"),
    (86, "critico", "critico"),           # histéresis: sigue crítico hasta < 85
    (84, "critico", "advertencia"),
    (40, "critico", "normal"),
])
def test_histeresis(valor, previo, esperado):
    assert N(valor, 75, 90, previo, 5) == esperado


def test_gestor_registra_eventos_solo_en_cambios():
    bit = Bitacora(archivo=False)
    g = GestorAlertas(bit)
    for v in (50, 80, 81, 82, 95, 96, 60):
        g.evaluar("cpu", v)
    niveles = [e["nivel"] for e in bit.listar()]
    assert niveles == ["advertencia", "critico", "info"]
    assert g.nivel("cpu") == "normal"


def test_configurar_valida():
    g = GestorAlertas(Bitacora(archivo=False))
    g.configurar("ram", 60, 70)
    assert g.listar_umbrales()["ram"]["advertencia"] == 60
    with pytest.raises(ValueError):
        g.configurar("ram", 90, 80)
    with pytest.raises(KeyError):
        g.configurar("inexistente", 1, 2)


def test_monitor_lectura_real():
    m = Monitor().leer()
    for k in ("cpu", "ram", "disco"):
        assert 0 <= m[k] <= 100
    assert m["ram_total_gb"] > 0
    assert isinstance(m["cpu_nucleos"], list) and m["cpu_nucleos"]


def test_monitor_procesos_ordenados():
    d = Monitor().procesos(limite=5, orden="ram")
    assert d["total"] > 0 and len(d["procesos"]) <= 5
    rams = [p["ram"] for p in d["procesos"]]
    assert rams == sorted(rams, reverse=True)


def test_info_sistema():
    i = Monitor.info_sistema()
    assert i["nucleos_logicos"] >= 1 and "administrador" in i
