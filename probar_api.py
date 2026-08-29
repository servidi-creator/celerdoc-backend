import urllib.request
import json

url = 'http://127.0.0.1:8000/api/firmar'
payload = {
    'pdf_entrada': 'documento_prueba.pdf',
    'pdf_salida': 'documento_api_final.pdf',
    'clave_path': 'key.pem',
    'cert_path': 'cert.pem',
    'nombres': 'JORGE IVAN BARRERA SANCHEZ',
    'cedula': 'C.C. 123456789',
    'codigo': 'CELERDOC-HASH-2026',
    'trazo': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as resp:
        print('Status:', resp.status)
        print('Response:', resp.read().decode('utf-8'))
except Exception as e:
    print('Error:', e)
