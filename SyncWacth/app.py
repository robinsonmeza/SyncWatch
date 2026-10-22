"""
SyncWatch — Monitor de recursos (P7) + Laboratorio de sincronización (P5)

Ejecutar:
    pip install -r requirements.txt
    python app.py            -> abre http://127.0.0.1:5000

Opciones:
    python app.py --puerto 8080 --sin-navegador
"""
from __future__ import annotations

import argparse
import logging
import socket
import threading
import time
import urllib.request
import webbrowser
from flask import Flask, Response, jsonify, request, send_from_directory

from core import escenarios
from core.alertas import GestorAlertas
from core.monitor import Monitor
from core.registro import Bitacora, RegistradorMetricas
from core.rutas import EMPAQUETADO, RECURSOS, REGISTROS
from core.simulador import Simulacion, comparar

app = Flask(__name__, static_folder=str(RECURSOS / "static"), static_url_path="/static")

# ------------------------------------------------------------------ estado global
bitacora = Bitacora()
alertas = GestorAlertas(bitacora)
monitor = Monitor(intervalo=1.0)
monitor.suscribir(alertas.evaluar_muestra_real)
registrador = RegistradorMetricas(monitor, bitacora, intervalo=2.0)

_lock_sim = threading.Lock()
simulacion: Simulacion | None = None
comparaciones: list = []
_cmp_estado = {"ejecutando": False, "resultado": None, "error": None}


# ---------------------------------------------------------------------- vistas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/sistema")
def api_sistema():
    return jsonify(monitor.info_sistema())


@app.get("/api/metricas")
def api_metricas():
    return jsonify({"actual": monitor.actual(), "historial": monitor.historial(),
                    "alertas": alertas.activas(), "registro": registrador.estado()})


@app.get("/api/procesos")
def api_procesos():
    orden = request.args.get("orden", "cpu")
    limite = int(request.args.get("limite", 8))
    return jsonify(monitor.procesos(limite=limite, orden=orden))


# -------------------------------------------------------------- laboratorio P5
@app.get("/api/escenarios")
def api_escenarios():
    return jsonify({"escenarios": escenarios.catalogo(), "limites": escenarios.LIMITES})


@app.post("/api/sim/iniciar")
def api_sim_iniciar():
    global simulacion
    datos = request.get_json(silent=True) or {}
    try:
        cfg = escenarios.construir(datos.get("escenario", "equilibrado"), datos.get("config"))
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    with _lock_sim:
        if simulacion and simulacion.activa:
            simulacion.detener("Reemplazada por una nueva simulación")
            simulacion.esperar(3)
        alertas.reiniciar("simulado")
        bitacora.registrar("info", "simulacion",
                           f"Escenario «{escenarios.ESCENARIOS[cfg['escenario']]['nombre']}» seleccionado")
        simulacion = Simulacion(cfg, bitacora, alertas)
        simulacion.iniciar()
    return jsonify({"ok": True, "config": cfg})


@app.post("/api/sim/detener")
def api_sim_detener():
    with _lock_sim:
        if simulacion and simulacion.activa:
            simulacion.detener()
    return jsonify({"ok": True})


@app.get("/api/sim/estado")
def api_sim_estado():
    with _lock_sim:
        s = simulacion
    if not s:
        return jsonify({"existe": False})
    return jsonify({"existe": True, **s.estado()})


@app.post("/api/comparar")
def api_comparar():
    if _cmp_estado["ejecutando"]:
        return jsonify({"error": "Ya hay una comparación en curso"}), 409
    datos = request.get_json(silent=True) or {}
    try:
        cfg = escenarios.construir("sin_sincronizacion", datos.get("config"))
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

    def tarea():
        _cmp_estado.update(ejecutando=True, resultado=None, error=None)
        try:
            r = comparar(cfg)
            r["id"] = len(comparaciones) + 1
            r["hora"] = time.strftime("%H:%M:%S")
            comparaciones.append(r)
            _cmp_estado["resultado"] = r
            s, c = r["sin"], r["con"]
            bitacora.registrar("advertencia" if not s["conservacion_ok"] else "info", "comparacion",
                               f"Comparación #{r['id']}: SIN sync -> perdidos {s['perdidos']}, duplicados "
                               f"{s['duplicados']}, lecturas vacías {s['lecturas_vacias']} | CON sync -> "
                               f"conservación {'OK' if c['conservacion_ok'] else 'FALLA'}")
        except Exception as e:  # pragma: no cover
            _cmp_estado["error"] = str(e)
        finally:
            _cmp_estado["ejecutando"] = False

    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True, "config": cfg})


@app.get("/api/comparar")
def api_comparar_estado():
    return jsonify({**_cmp_estado, "historial": comparaciones[-10:]})


# ---------------------------------------------------- alertas, registro, eventos
@app.get("/api/umbrales")
def api_umbrales():
    return jsonify(alertas.listar_umbrales())


@app.post("/api/umbrales")
def api_umbrales_guardar():
    datos = request.get_json(silent=True) or {}
    errores = {}
    for metrica, u in datos.items():
        try:
            alertas.configurar(metrica, u["advertencia"], u["critico"])
        except (KeyError, ValueError, TypeError) as e:
            errores[metrica] = str(e)
    return jsonify({"ok": not errores, "errores": errores, "umbrales": alertas.listar_umbrales()}), \
        (200 if not errores else 400)


@app.get("/api/eventos")
def api_eventos():
    return jsonify(bitacora.listar(nivel=request.args.get("nivel") or None,
                                   origen=request.args.get("origen") or None,
                                   desde_id=int(request.args.get("desde", 0)),
                                   limite=int(request.args.get("limite", 200))))


@app.post("/api/registro")
def api_registro():
    datos = request.get_json(silent=True) or {}
    if datos.get("activo"):
        if registrador.activo and datos.get("intervalo") and float(datos["intervalo"]) != registrador.intervalo:
            registrador.detener()
        registrador.iniciar(datos.get("intervalo"))
    else:
        registrador.detener()
    return jsonify(registrador.estado())


@app.get("/api/exportar/<tipo>")
def api_exportar(tipo):
    if tipo == "metricas":
        contenido, nombre = registrador.contenido(), registrador.estado()["archivo"] or "metricas.csv"
    elif tipo == "eventos":
        contenido, nombre = bitacora.csv(), "eventos.csv"
    else:
        return jsonify({"error": "tipo inválido"}), 404
    return Response(contenido, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


# ------------------------------------------------------------------------ main
def _puerto_libre(preferido: int) -> int:
    """Devuelve el primer puerto libre desde `preferido` (hasta +20)."""
    for p in range(preferido, preferido + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("No hay puertos libres entre %d y %d" % (preferido, preferido + 19))


def _ya_abierto(puerto: int) -> bool:
    """¿Ya hay un SyncWatch respondiendo en ese puerto? (evita abrir dos copias)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/sistema", timeout=1) as r:
            return "nucleos_logicos" in r.read().decode("utf-8", "ignore")
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description="SyncWatch")
    p.add_argument("--puerto", type=int, default=5000)
    p.add_argument("--sin-navegador", action="store_true")
    args = p.parse_args()

    if _ya_abierto(args.puerto):
        print(f"SyncWatch ya está en ejecución: se abre http://127.0.0.1:{args.puerto}")
        if not args.sin_navegador:
            webbrowser.open(f"http://127.0.0.1:{args.puerto}")
        return
    puerto = _puerto_libre(args.puerto)

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    monitor.iniciar()
    info = monitor.info_sistema()
    bitacora.registrar("info", "sistema", f"SyncWatch iniciado en {info['equipo']} ({info['so']}), "
                                          f"Python {info['python']}, psutil {info['psutil']}"
                                          + (" · ejecutable empaquetado" if EMPAQUETADO else ""))
    if not info["administrador"]:
        bitacora.registrar("advertencia", "sistema",
                           "Sin privilegios de administrador: algunos procesos mostrarán datos restringidos")
    if not info["temperatura_disponible"]:
        bitacora.registrar("info", "sistema",
                           "El sistema operativo no expone la temperatura a psutil (habitual en Windows)")
    url = f"http://127.0.0.1:{puerto}"
    print("\n  ==============================================")
    print("   SyncWatch  ·  Monitor + Laboratorio de sync")
    print("  ==============================================")
    print(f"   Panel:      {url}")
    print(f"   Registros:  {REGISTROS}")
    print("   Para salir: cierre esta ventana o pulse Ctrl+C\n")
    if not args.sin_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=puerto, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
