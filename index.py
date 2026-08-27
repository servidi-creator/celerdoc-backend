import os
import base64
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from sello_criptografico import procesar_firma_completa, calcular_sha256

app = FastAPI(title="Celerdoc API - Sistema de Firma y Auditoría")

# Habilitar CORS para permitir peticiones desde el frontend local o remoto
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carpetas de almacenamiento
CARPETA_ORIGINALES = "documentos_originales"
CARPETA_FIRMADOS = "respaldos_auditados"

os.makedirs(CARPETA_ORIGINALES, exist_ok=True)
os.makedirs(CARPETA_FIRMADOS, exist_ok=True)

class DocumentoPayload(BaseModel):
    nombre_archivo: str
    archivo_base64: str
    tipo_documento: str
    numero_documento: str
    total_firmantes: Optional[int] = 1
    pagina_seleccionada: Optional[int] = 1
    coordenadas: Optional[Dict[str, float]] = {"x_pct": 50.0, "y_pct": 80.0}
    email_notificacion: Optional[str] = None
    whatsapp_notificacion: Optional[str] = None

@app.get("/")
def estado_api():
    return {"estado": "activo", "servicio": "Celerdoc Engine", "version": "2.0"}

@app.post("/procesar-firma")
def api_procesar_firma(payload: DocumentoPayload):
    try:
        # 1. Decodificar el archivo binario enviado por el usuario
        pdf_bytes = base64.b64decode(payload.archivo_base64)
        
        # 2. Guardar el PDF original intacto en la carpeta de originales
        ruta_guardado_original = os.path.join(CARPETA_ORIGINALES, payload.nombre_archivo)
        with open(ruta_guardado_original, "wb") as f:
            f.write(pdf_bytes)
            
        sha256_original = calcular_sha256(ruta_guardado_original)

        # 3. Construir la nomenclatura exacta del PDF final
        nombre_base = os.path.splitext(payload.nombre_archivo)[0]
        timestamp_sufijo = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_final = f"{nombre_base}_{payload.tipo_documento}_{payload.numero_documento}_{timestamp_sufijo}.pdf"
        ruta_guardado_final = os.path.join(CARPETA_FIRMADOS, nombre_final)

        # 4. Procesar sellado, desborde (1 a N páginas) y hoja de auditoría
        datos_firmante = {
            "tipo_documento": payload.tipo_documento,
            "numero_documento": payload.numero_documento,
            "total_firmantes": payload.total_firmantes,
            "pagina_seleccionada": payload.pagina_seleccionada,
            "coordenadas": payload.coordenadas,
            "timestamp_carga_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        }

        resultado = procesar_firma_completa(
            ruta_pdf_original=ruta_guardado_original,
            datos_firmante=datos_firmante,
            ruta_destino_final=ruta_guardado_final
        )

        return {
            "exito": True,
            "mensaje": "Documento firmado, sellado y auditado con total éxito.",
            "datos_archivo": {
                "nombre_original": payload.nombre_archivo,
                "nombre_final": nombre_final,
                "ruta_descarga": f"/descargar/{nombre_final}",
                "ruta_servidor": ruta_guardado_final
            },
            "criptografia_trazabilidad": {
                "sha256_original": resultado["sha256_original"],
                "sha256_final": resultado["sha256_final"],
                "codigo_validador": resultado["codigo_validador"],
                "total_paginas_final": resultado["total_paginas_final"]
            },
            "notificaciones_programadas": {
                "email": payload.email_notificacion,
                "whatsapp": payload.whatsapp_notificacion
            }
        }

    except Exception as e:
        raise HTTPException(status_status=500, detail=str(e))

@app.get("/descargar/{nombre_archivo}")
def descargar_documento(nombre_archivo: str):
    ruta_archivo = os.path.join(CARPETA_FIRMADOS, nombre_archivo)
    if not os.path.exists(ruta_archivo):
        raise HTTPException(status_code=404, detail="El archivo solicitado no existe.")
    return FileResponse(
        ruta_archivo,
        media_type="application/pdf",
        filename=nombre_archivo
    )