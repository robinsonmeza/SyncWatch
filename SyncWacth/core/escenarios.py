"""
escenarios.py — Configuraciones predefinidas del laboratorio.

Tiempos en segundos por ítem (se aplica una variación aleatoria de ±30 %
generada con la semilla, para que la ejecución sea repetible).
"""

BASE = {
    "sincronizado": True,
    "capacidad": 8,
    "productores": 2,
    "consumidores": 2,
    "items_por_productor": 25,
    "t_produccion": 0.25,
    "t_consumo": 0.25,
    "ventana": 0.003,       # solo modo sin sincronización
    "carga": "normal",      # normal | stress | fuga
    "semilla": 42,
    "duracion_max": 90,
}

ESCENARIOS = {
    "equilibrado": {
        "nombre": "Equilibrado",
        "descripcion": "Productores y consumidores al mismo ritmo. El búfer oscila sin llenarse ni vaciarse del todo.",
        "observar": "Flujo estable, pocos bloqueos y la regla de conservación siempre se cumple.",
        "config": {},
    },
    "productores_rapidos": {
        "nombre": "Productores rápidos",
        "descripcion": "Tres productores veloces y un consumidor lento.",
        "observar": "El búfer se LLENA y los productores quedan BLOQUEADOS en el semáforo espacios_libres.",
        "config": {"capacidad": 6, "productores": 3, "consumidores": 1,
                   "items_por_productor": 12, "t_produccion": 0.08, "t_consumo": 0.35},
    },
    "consumidores_rapidos": {
        "nombre": "Consumidores rápidos",
        "descripcion": "Un productor lento y tres consumidores veloces.",
        "observar": "El búfer queda VACÍO y los consumidores quedan BLOQUEADOS en el semáforo items_disponibles.",
        "config": {"capacidad": 6, "productores": 1, "consumidores": 3,
                   "items_por_productor": 25, "t_produccion": 0.3, "t_consumo": 0.05},
    },
    "sin_sincronizacion": {
        "nombre": "Sin sincronización",
        "descripcion": "Mismo problema, pero el búfer no usa mutex ni semáforos.",
        "observar": "Condición de carrera: ítems perdidos, duplicados, lecturas vacías y la cuenta del búfer deja de ser real.",
        "config": {"sincronizado": False, "productores": 3, "consumidores": 3,
                   "items_por_productor": 30, "t_produccion": 0.15, "t_consumo": 0.15, "ventana": 0.03},
    },
    "stress_cpu": {
        "nombre": "Stress test CPU/GPU",
        "descripcion": "Muchos workers y una carga simulada que sube de forma progresiva.",
        "observar": "La CPU/GPU y la temperatura simuladas cruzan los umbrales: alerta, throttling y autoprotección.",
        "config": {"capacidad": 10, "productores": 4, "consumidores": 4,
                   "items_por_productor": 200, "t_produccion": 0.12, "t_consumo": 0.14, "carga": "stress"},
    },
    "fuga_ram": {
        "nombre": "Fuga de memoria",
        "descripcion": "Cada ítem consumido deja memoria sin liberar (simulado).",
        "observar": "La RAM simulada crece sin parar hasta la alerta crítica y la simulación se detiene.",
        "config": {"capacidad": 10, "productores": 2, "consumidores": 2,
                   "items_por_productor": 200, "t_produccion": 0.12, "t_consumo": 0.12, "carga": "fuga"},
    },
    "personalizado": {
        "nombre": "Personalizado",
        "descripcion": "Tú eliges todos los parámetros.",
        "observar": "Prueba combinaciones y compara con los escenarios anteriores.",
        "config": {},
    },
}

LIMITES = {
    "capacidad": (1, 20), "productores": (1, 8), "consumidores": (1, 8),
    "items_por_productor": (1, 500), "t_produccion": (0.01, 3.0), "t_consumo": (0.01, 3.0),
    "ventana": (0.0, 0.05), "duracion_max": (5, 600),
}


def construir(clave: str, cambios: dict | None = None) -> dict:
    """Devuelve la configuración final de un escenario, validando los límites."""
    if clave not in ESCENARIOS:
        raise KeyError(f"Escenario desconocido: {clave}")
    cfg = dict(BASE)
    cfg.update(ESCENARIOS[clave]["config"])
    for k, v in (cambios or {}).items():
        if k in BASE and v is not None and v != "":
            cfg[k] = v
    for k, (lo, hi) in LIMITES.items():
        tipo = int if isinstance(BASE[k], int) else float
        cfg[k] = min(hi, max(lo, tipo(cfg[k])))
    cfg["sincronizado"] = bool(cfg["sincronizado"]) if not isinstance(cfg["sincronizado"], str) \
        else cfg["sincronizado"].lower() in ("1", "true", "si", "sí")
    cfg["semilla"] = int(cfg["semilla"])
    if cfg["carga"] not in ("normal", "stress", "fuga"):
        cfg["carga"] = "normal"
    cfg["escenario"] = clave
    return cfg


def catalogo() -> list:
    return [{"clave": k, "nombre": v["nombre"], "descripcion": v["descripcion"],
             "observar": v["observar"], "config": construir(k)} for k, v in ESCENARIOS.items()]
