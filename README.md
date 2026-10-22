# SyncWatch
**PROYECTO FINAL - SISTEMAS OPERATIVOS**
**Monitor de recursos (Proyecto 7 · SysWatch) + Laboratorio de sincronización (Proyecto 5 · SyncLab)**
Sistemas Operativos · Nayelin Castillo · Robinson Meza

SyncWatch lee las métricas **reales** del equipo donde se ejecuta (CPU, RAM, disco y procesos) y, en el mismo panel, ofrece un **laboratorio simulado** de stress test construido sobre el problema productor‑consumidor con búfer compartido.

| | Real (psutil) | Simulado |
|---|---|---|
| Qué es | CPU total y por núcleo, RAM, swap, disco, procesos, temperatura (si el SO la expone) | Carga del stress test (CPU/GPU/RAM/temperatura), trabajo de productores y consumidores |
| Dónde se ve | Pestaña **Monitor**, registro CSV | Pestañas **Laboratorio** y **Comparación** |
| Etiqueta en la interfaz | `REAL` | `SIMULADO` |

---

## 1. Instalación y ejecución (Solo Windows)

### Opción A — Instalador (equipos nuevos, sin Python)

1. Ejecute `SyncWatch_Instalador_1.0.0.exe`.
2. Siga el asistente: no pide permisos de administrador y ofrece crear un acceso directo en el escritorio.
3. Abra **SyncWatch** desde el menú Inicio o el escritorio. Se abre una ventana de consola (la URL y la carpeta de registros) y el panel en el navegador. Cerrar la consola detiene el programa.

Alternativa sin instalar: copie `SyncWatch.exe` a cualquier carpeta y ejecútelo con doble clic. El archivo lleva dentro Python, psutil, Flask y la interfaz.

**Dónde quedan los datos:** `CARPETA DE DESTINO\SyncWatch\registros` (CSV de métricas y `eventos.log`). Desinstalar el programa no borra esta carpeta, así las evidencias se conservan.

> Windows SmartScreen o el antivirus pueden avisar la primera vez porque el ejecutable no está firmado digitalmente. Pulse **Más información → Ejecutar de todas formas**. Es normal en programas académicos empaquetados con PyInstaller.

### Opción B — Construir el `.exe` y el instalador (una sola vez)

Requisitos: Python 3.10+ e internet. Doble clic en **`construir_exe.bat`**. El script:

1. Crea un entorno aislado `.venv-build` e instala las dependencias y PyInstaller.
2. Ejecuta las 32 pruebas y guarda el resultado en `evidencias\pruebas_pytest_windows.txt`. Si alguna falla, se detiene.
3. Genera `dist\SyncWatch.exe` con PyInstaller (receta `SyncWatch.spec`).
4. Genera `dist\SyncWatch_Instalador_1.0.0.exe` con Inno Setup (receta `instalador.iss`). Si Inno Setup no está instalado, ofrece instalarlo con `winget`; si no, entrega solo `SyncWatch.exe`.

Esos dos archivos de `dist\` son los que se copian a cualquier otro equipo.

### Opción C — Desde el código fuente

Requisitos: **Python 3.10 o superior** (probado con 3.13).

**Rápida:** doble clic en `iniciar.bat`. La primera vez crea un entorno virtual e instala las dependencias.

**Manual (PowerShell o CMD, dentro de la carpeta del proyecto):**

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Se abre el navegador en `http://127.0.0.1:5000`. Para salir: `Ctrl + C` en la consola.

Opciones: `python app.py --puerto 8080 --sin-navegador` (también sirven con `SyncWatch.exe`).

Si el puerto 5000 está ocupado se usa el siguiente libre. Si SyncWatch ya está abierto, una segunda ejecución solo abre el navegador en lugar de iniciar otra copia.

**Ejecutar las pruebas:**

```bash
python -m pytest
```

## 2. Dependencias

| Paquete | Uso | Por qué |
|---|---|---|
| `psutil` | Lectura de CPU, RAM, disco y procesos | Multiplataforma; abstrae las APIs del SO (en Windows usa las del kernel, en Linux `/proc`) |
| `Flask` | Servidor web local que sirve el dashboard y la API JSON | Ligero; permite una interfaz moderna en el navegador sin instalar nada más |
| `pytest` | Pruebas automatizadas | Evidencia de los casos de prueba |
| `PyInstaller` (solo para construir) | Empaqueta Python + dependencias + interfaz en `SyncWatch.exe` | El equipo destino no necesita Python |
| Inno Setup 6 (solo para construir) | Crea el instalador con accesos directos y desinstalador | Instalación estándar de Windows, por usuario |
| Chart.js 4.4.1 | Gráficos del dashboard | Incluido en `static/vendor/`; **funciona sin internet** |

## 3. Estructura

```
SyncWatch/
├── app.py                # servidor Flask + API
├── iniciar.bat           # arranque desde el código (requiere Python)
├── construir_exe.bat     # genera dist\SyncWatch.exe y el instalador
├── SyncWatch.spec        # receta de PyInstaller
├── instalador.iss        # receta de Inno Setup
├── assets/syncwatch.ico  # icono de la aplicación
├── core/
│   ├── rutas.py          # rutas de recursos y datos (código fuente o .exe)
│   ├── monitor.py        # P7 · lecturas reales con psutil (hilo muestreador + caché con Lock)
│   ├── registro.py       # P7 · bitácora de eventos y registro CSV por intervalos
│   ├── alertas.py        # P7 · umbrales (advertencia/crítico) con histéresis
│   ├── buffer.py         # P5 · BufferSincronizado (mutex + 2 semáforos) y BufferInseguro
│   ├── simulador.py      # P5 · hilos productores/consumidores, carga simulada, auditoría
│   └── escenarios.py     # P5 · 7 escenarios predefinidos
├── static/               # dashboard (HTML/CSS/JS, estilo liquid glass)
├── tests/                # 32 pruebas con pytest
└── registros/            # desde el código: eventos.log y metricas_*.csv
                          # (con el .exe: Documentos\SyncWatch\registros)
```

## 4. Cómo se fusionan los dos proyectos

- El **monitor real** ya es en sí un productor‑consumidor: un hilo *muestreador* produce lecturas y la API, el registrador y las alertas las consumen desde una caché protegida por un `Lock`.
- El **laboratorio** modela un stress test: los *productores* generan tareas, el *búfer* las encola y los *workers* (consumidores) las procesan. La actividad de los workers alimenta un modelo de carga simulada de CPU, GPU, RAM y temperatura.
- El **sistema de alertas de P7** vigila tanto las métricas reales como las simuladas. En el stress test reacciona solo: activa el *throttling* y, si no basta, la *autoprotección*.

## 5. Papel del mutex y los semáforos

```
productor:   P(espacios_libres) → P(mutex) → insertar → V(mutex) → V(items_disponibles)
consumidor:  P(items_disponibles) → P(mutex) → extraer → V(mutex) → V(espacios_libres)
```

| Primitiva | Valor inicial | Protege contra |
|---|---|---|
| `mutex` (`threading.Lock`) | libre | Que dos hilos modifiquen a la vez `entrada`, `salida` y `cuenta` (sección crítica) |
| `espacios_libres` (`Semaphore`) | capacidad | Insertar en un búfer **lleno**: el productor se bloquea |
| `items_disponibles` (`Semaphore`) | 0 | Extraer de un búfer **vacío**: el consumidor se bloquea |

El orden importa: si un productor tomara primero el mutex y luego esperara en `espacios_libres` con el búfer lleno, ningún consumidor podría entrar a liberar espacio → **interbloqueo (deadlock)**.

## 6. Escenarios

| # | Escenario | Qué demuestra |
|---|---|---|
| 1 | Equilibrado | Flujo estable; la conservación se cumple |
| 2 | Productores rápidos | Búfer **lleno** → productores **bloqueados** en `espacios_libres` |
| 3 | Consumidores rápidos | Búfer **vacío** → consumidores **bloqueados** en `items_disponibles` |
| 4 | Sin sincronización | **Condición de carrera**: ítems perdidos, duplicados, lecturas vacías y cuenta incorrecta |
| 5 | Stress test CPU/GPU | Rampa de carga → alertas → throttling → autoprotección |
| 6 | Fuga de memoria | La RAM simulada crece hasta el nivel crítico y la simulación se detiene |
| 7 | Personalizado | Todos los parámetros configurables |

## 7. Reto de experimentación (P5)

Pestaña **Comparación**: ejecuta la *misma* configuración con y sin sincronización, en paralelo, y verifica la regla de conservación:

> **producidos = consumidos únicos + en búfer**, con 0 perdidos, 0 duplicados y 0 lecturas vacías.

La versión insegura comprueba "¿hay espacio?" y luego escribe; entre ambos pasos se fuerza un cambio de contexto (`sleep` de 0 a 3 ms), así que dos hilos pueden leer el mismo índice. El auditor es confiable porque cada hilo anota sus ítems en una lista **privada**.

Resultado típico (3 productores, 3 consumidores, capacidad 8, 30 ítems c/u):

| | Sin sincronización | Con mutex + semáforos |
|---|---|---|
| Producidos | 90 | 90 |
| Consumidos | ~65–85 | 90 |
| Perdidos | ~20–40 | **0** |
| Duplicados | ~10–30 | **0** |
| Conservación | **FALLA** | **OK** |

Los números de la versión insegura cambian en cada ejecución (no determinismo de la planificación de hilos), pero **siempre** hay anomalías; la versión sincronizada **siempre** cumple la regla.

## 8. Casos de prueba (`tests/`)

| Prueba | Verifica |
|---|---|
| `test_productor_se_bloquea_con_buffer_lleno` | Capacidad 2: el 3.er `insertar` se bloquea y la cuenta no pasa de 2 |
| `test_consumidor_se_bloquea_con_buffer_vacio_y_despierta` | `extraer` duerme con el búfer vacío y despierta con `V(items)` |
| `test_sincronizado_nunca_desborda[1,3,8]` | 4 productores × 4 consumidores × 200 ítems: sin pérdidas, duplicados ni desbordes |
| `test_inseguro_produce_condicion_de_carrera` | Sin sincronización aparecen anomalías |
| `test_conservacion_con_sincronizacion[...]` | Escenarios 1–3 cumplen la regla de conservación |
| `test_comparacion_sin_vs_con[1,2,3]` | Con 3 semillas distintas: sin sync falla y con sync es correcto |
| `test_stress_dispara_throttling_y_autoproteccion` | El escenario 5 activa throttling y se autodetiene |
| `test_fuga_ram_detiene_simulacion` | El escenario 6 se detiene por RAM crítica |
| `test_histeresis[...]` | 8 casos de la regla de umbrales con histéresis |
| `test_monitor_*` | Las lecturas reales están en rango y los procesos se ordenan |

## 9. Limitaciones conocidas

- **Temperatura:** en Windows psutil no expone sensores de temperatura (`sensors_temperatures` solo existe en Linux/FreeBSD). Por eso la temperatura del laboratorio es simulada.
- **Permisos:** sin ejecutar como administrador, algunos procesos del sistema niegan el acceso (`AccessDenied`) a su usuario o memoria; se muestran como "restringidos" y se cuentan en la interfaz.
- **CPU instantánea:** `cpu_percent()` compara con la lectura anterior. Se usa un solo hilo muestreador cada 1 s; los picos de menos de 1 s pueden no verse.
- **CPU por proceso:** puede superar 100 % en equipos multinúcleo; se normaliza dividiendo por los núcleos lógicos. La primera lectura de un proceso nuevo vale 0 %.
- **Disco:** solo la unidad principal (`C:\`).
- **GPU:** psutil no la mide; aquí solo existe en la simulación.
- **GIL de Python:** los hilos no ejecutan cálculo en paralelo real. No afecta al experimento, porque lo que se estudia es el *acceso concurrente* al búfer (los `sleep` liberan el GIL y permiten el intercalado), pero un stress test real de CPU necesitaría `multiprocessing`.
- **Simulación vs. realidad:** la carga del stress test es un modelo numérico (con inercia térmica, throttling y fuga de memoria), no una medición. El equipo no se calienta.
- **Reproducibilidad:** la semilla fija los tiempos de trabajo de cada hilo, pero el planificador del SO decide el intercalado, así que los conteos exactos de anomalías varían entre ejecuciones.

## 10. Justificación del enfoque (P5: "hilos reales o simulación")

Se usan **hilos reales** (`threading.Thread`) y **primitivas reales** (`Lock`, `Semaphore`): los bloqueos y la condición de carrera ocurren de verdad en el intérprete; no son una animación. Lo único simulado es **el trabajo** (`sleep`), para que el experimento sea seguro, rápido, visual y repetible.

## 11. Pendientes

| Pendiente | Descripción | Estado |
|---|---|---|
| Instalador `.exe` | `SyncWatch.exe` autocontenido + instalador Inno Setup. Las recetas están listas y el empaquetado se verificó (build de prueba: el panel, la API, la comparación y el registro CSV funcionan desde el ejecutable). Falta ejecutar `construir_exe.bat` en Windows, porque PyInstaller no genera `.exe` de Windows desde otro sistema. | Listo para construir |
| Informe | Documento con arquitectura, papel de mutex y semáforos, experimento de condición de carrera, casos de prueba, evidencias y limitaciones. Requiere capturas y un CSV de registro tomados en el equipo real. | Pendiente |
| Presentación | Unas 10 diapositivas para la sustentación (exportables a PowerPoint). | Pendiente |
| Evidencias en el equipo real | Capturas de las 4 pestañas, un `metricas_*.csv` y `eventos.log` tomados en Windows. La salida de las pruebas en Windows la genera `construir_exe.bat` en `evidencias\pruebas_pytest_windows.txt`. | Pendiente |

Mientras no se construya el `.exe`, el arranque en Windows se hace con `iniciar.bat` (requiere Python).
