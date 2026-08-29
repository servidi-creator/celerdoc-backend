import os
import sys
from io import BytesIO

# Asegurar rutas de importación (carpeta actual y raíz del proyecto)
dir_actual = os.path.dirname(os.path.abspath(__file__))
dir_raiz = os.path.abspath(os.path.join(dir_actual, "../.."))

if dir_actual not in sys.path:
    sys.path.insert(0, dir_actual)
if dir_raiz not in sys.path:
    sys.path.insert(0, dir_raiz)

from firmador import generar_apariencia_firma
from sello_criptografico import firmar_documento

trazo_dummy = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
output_stream = BytesIO()

# 1. Probar generación visual de apariencia
generar_apariencia_firma(
    trazo_base64=trazo_dummy,
    nombres="JORGE IVAN BARRERA SANCHEZ",
    identificacion="C.C. 123456789",
    codigo_verificacion="HASH-SHA256-TEST998877",
    output_stream=output_stream,
)
print("Éxito: Bloque de firma generado correctamente.")

# 2. Probar estampado y firmado criptográfico
firmar_documento(
    "documento_prueba.pdf",
    "documento_final.pdf",
    "key.pem",
    "cert.pem",
    "JORGE IVAN BARRERA SANCHEZ",
    "C.C. 123456789",
    "CELERDOC-HASH-2026",
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
)
print("Éxito: Prueba de firmar_documento ejecutada correctamente.")