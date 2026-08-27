from io import BytesIO
from json_firmas.firmador import generar_apariencia_firma

trazo_dummy = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
output_stream = BytesIO()
generar_apariencia_firma(trazo_base64=trazo_dummy, nombres='JORGE IVAN BARRERA SANCHEZ', identificacion='C.C. 123456789', codigo_verificacion='HASH-SHA256-TEST998877', output_stream=output_stream)
print('Exito! Bloque de firma generado correctamente.')
