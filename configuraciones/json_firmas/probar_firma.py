import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from sello_criptografico import firmar_documento
firmar_documento('documento_prueba.pdf', 'documento_final.pdf', 'key.pem', 'cert.pem', 'JORGE IVAN BARRERA SANCHEZ', 'C.C. 123456789', 'CELERDOC-HASH-2026', 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
print('Prueba de firmar_documento ejecutada con éxito.')
