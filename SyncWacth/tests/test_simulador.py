"""Pruebas del simulador, escenarios y experimento de comparación."""
import pytest

from core import escenarios
from core.alertas import GestorAlertas
from core.registro import Bitacora
from core.simulador import Simulacion, comparar

RAPIDO = {"t_produccion": 0.02, "t_consumo": 0.02}


def correr(clave, cambios=None, alertas=False):
    cfg = escenarios.construir(clave, {**RAPIDO, **(cambios or {})})
    bit = Bitacora(archivo=False)
    s = Simulacion(cfg, bit, GestorAlertas(bit) if alertas else None)
    s.iniciar()
    s.esperar(60)
    return s


def test_construir_respeta_limites():
    cfg = escenarios.construir("personalizado", {"capacidad": 999, "productores": 0, "t_consumo": -1})
    assert cfg["capacidad"] == 20 and cfg["productores"] == 1 and cfg["t_consumo"] == 0.01


def test_escenario_desconocido():
    with pytest.raises(KeyError):
        escenarios.construir("no_existe")


@pytest.mark.parametrize("clave", ["equilibrado", "productores_rapidos", "consumidores_rapidos"])
def test_conservacion_con_sincronizacion(clave):
    s = correr(clave, {k: v for k, v in RAPIDO.items()} if clave == "equilibrado" else {})
    a = s.auditoria()
    total = s.cfg["productores"] * s.cfg["items_por_productor"]
    assert a["conservacion_ok"]
    assert a["producidos"] == a["consumidos"] == total
    assert a["perdidos"] == a["duplicados"] == a["lecturas_vacias"] == 0


def test_productores_rapidos_bloquea_productores():
    s = correr("productores_rapidos", {})
    assert sum(h.bloqueos for h in s.productores) > 0


def test_consumidores_rapidos_bloquea_consumidores():
    s = correr("consumidores_rapidos", {})
    assert sum(h.bloqueos for h in s.consumidores) > 0


@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_comparacion_sin_vs_con(semilla):
    cfg = escenarios.construir("sin_sincronizacion", {**RAPIDO, "items_por_productor": 30, "semilla": semilla})
    r = comparar(cfg)
    assert r["con"]["conservacion_ok"] is True
    assert r["sin"]["conservacion_ok"] is False
    assert r["sin"]["perdidos"] + r["sin"]["duplicados"] + r["sin"]["lecturas_vacias"] > 0


def test_stress_dispara_throttling_y_autoproteccion():
    s = correr("stress_cpu", {"items_por_productor": 500, "t_produccion": 0.12, "t_consumo": 0.14}, alertas=True)
    assert s.throttling
    assert "Autoprotección" in s.motivo_fin
    assert s.auditoria()["conservacion_ok"]          # parar a mitad no corrompe el búfer


def test_fuga_ram_detiene_simulacion():
    s = correr("fuga_ram", {"items_por_productor": 500}, alertas=True)
    assert "fuga" in s.motivo_fin.lower()
    assert s.carga["ram_sim"] >= 90
