"""
rutas.py — Ubicación de recursos y datos, tanto en desarrollo como empaquetado.

- En desarrollo (python app.py): todo vive junto al código.
- Empaquetado con PyInstaller (SyncWatch.exe): los archivos de la interfaz se
  extraen a una carpeta temporal (sys._MEIPASS) y la carpeta del programa puede
  no tener permisos de escritura (p. ej. Archivos de programa). Por eso los
  registros se guardan en  Documentos\\SyncWatch\\registros  del usuario.
  Se puede cambiar con la variable de entorno SYNCWATCH_DATOS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

EMPAQUETADO = bool(getattr(sys, "frozen", False))
CODIGO = Path(__file__).resolve().parent.parent

# Recursos de solo lectura (HTML, CSS, JS)
RECURSOS = Path(getattr(sys, "_MEIPASS", CODIGO))


def _carpeta_datos() -> Path:
    if os.environ.get("SYNCWATCH_DATOS"):
        return Path(os.environ["SYNCWATCH_DATOS"])
    if not EMPAQUETADO:
        return CODIGO / "registros"
    return _documentos() / "SyncWatch" / "registros"


def _documentos() -> Path:
    """Carpeta Documentos real del usuario (respeta la redirección de OneDrive en Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5 -> "Documentos" tal como lo ve el Explorador
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    docs = Path.home() / "Documents"
    return docs if docs.exists() else Path.home()


REGISTROS = _carpeta_datos()
