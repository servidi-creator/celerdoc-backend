from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import urllib.request
import os
from datetime import datetime
import hashlib
import shutil

app = FastAPI(title="Celerdoc Master Backend", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CARPETA_ORIGINALES = "respaldos_originales"
CARPETA_FIRMADOS = "documentos_firmados"
os.makedirs(CARPETA_ORIGINALES, exist_ok=True)
os.makedirs(CARPETA_FIRMADOS, exist_ok=True)

MAPEO_TIPO_DOC = {
    "Cédula de Ciudadanía": "CC",
    "Cédula de Extranjería": "CE",
    "NIT": "NIT",
    "Pasaporte": "PP"
}

OTP_SIMULADO_PRUEBAS = "123456"

@app.get("/")
def mostrar_vitrina():
    orig = os.listdir(CARPETA_ORIGINALES) if os.path.exists(CARPETA_ORIGINALES) else []
    firm = os.listdir(CARPETA_FIRMADOS) if os.path.exists(CARPETA_FIRMADOS) else []
    return {
        "estado": "ok", 
        "mensaje": "Master Backend de Celerdoc v2.1 operando",
        "respaldos_originales": orig,
        "documentos_firmados": firm
    }

@app.post("/api/v1/firmas/procesar-master-integral")
async def procesar_master_integral(request: Request):
    try:
        datos_wix = await request.json()
        submissions = datos_wix.get('data', {}).get('submissions', [])
        campos = {item['label']: item['value'] for item in submissions}
        
        nombre = campos.get('nombre', 'SinNombre')
        apellido = campos.get('apellido', 'SinApellido')
        email_usuario = campos.get('email_usuario', 'SinCorreo')
        tipo_doc_largo = campos.get('tipo_documento', 'CC')
        numero_doc = campos.get('numero_documento', '000000')
        url_pdf = campos.get('archivo_pdf', '')
        
        acepta_terminos = campos.get('terminos_condiciones', False)
        codigo_otp_ingresado = campos.get('codigo_otp', '')
        
        if not acepta_terminos or str(acepta_terminos).lower() in ['false', '0', 'no']:
            return {
                "estado": "error", 
                "mensaje": "Debe aceptar obligatoriamente los Términos y Condiciones para continuar con la firma."
            }
            
        if codigo_otp_ingresado != OTP_SIMULADO_PRUEBAS:
            return {
                "estado": "error", 
                "mensaje": "Código OTP inválido o incorrecto. Verifique el código de 6 dígitos."
            }
            
        if not url_pdf:
            return {"estado": "error", "mensaje": "Wix no envió ningún enlace al PDF."}
            
        tipo_doc = MAPEO_TIPO_DOC.get(tipo_doc_largo, tipo_doc_largo.upper()[:3])
        
        timestamp_str = datetime.now().strftime('%Y%m%d_%H-%M-%S')
        nombre_original_archivo = f"documento_{timestamp_str}.pdf"
        ruta_original = os.path.join(CARPETA_ORIGINALES, nombre_original_archivo)
        
        urllib.request.urlretrieve(url_pdf, ruta_original)
        
        sha256_hash = hashlib.sha256()
        with open(ruta_original, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        hash_original = sha256_hash.hexdigest()
        
        nombre_final = f"COMODATO_{tipo_doc}_{numero_doc}_{timestamp_str}.pdf"
        ruta_final = os.path.join(CARPETA_FIRMADOS, nombre_final)
        
        shutil.copyfile(ruta_original, ruta_final)
        
        return {
            "estado": "exitoso",
            "mensaje": "¡Candados superados con éxito! Documento procesado, validado por OTP y archivado de forma segura.",
            "firmante": f"{nombre} {apellido}",
            "usuario": email_usuario,
            "documento_original": nombre_original_archivo,
            "documento_firmado": nombre_final,
            "sha256_original": hash_original,
            "timestamp": str(datetime.now())
        }
        
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}