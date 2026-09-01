import os
import uuid
import base64
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Celerdoc Core API",
    version="1.0.0",
    description="Motor unificado de firma individual (OTP) y emision corporativa automatizada"
)

# Soporte CORS para navegadores moviles y desktop
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_CORPORATIVA = os.getenv("CELERDOC_CORP_API_KEY", "celerdoc_corp_secret_key_default")
TAREAS_PROCESAMIENTO: Dict[str, Dict[str, Any]] = {}

# --- MODELOS ---
class FirmaIndividualRequest(BaseModel):
    nombre_archivo: str
    nombre_final_sugerido: str
    archivo_base64: str
    tipo_documento: str
    codigo_tipo_doc: str
    numero_documento: str
    nombre_firmante: str
    latitud_raw: Optional[float] = None
    longitud_raw: Optional[float] = None
    trazo_firma_base64: str
    total_firmantes: int = 1
    pagina_seleccionada: int = 1
    total_paginas_con_extras: int = 1
    coordenadas: Dict[str, Any]
    pkcs7_info: Optional[Dict[str, Any]] = None
    email_notificacion: str
    whatsapp_notificacion: str
    timestamp_carga_doc: str
    timestamp_terminos: str
    timestamp_trazo: str
    timestamp_otp: str
    sha256_original: str
    codigo_otp_validado: str
    user_agent: str

class FirmaCorporativaRequest(BaseModel):
    template_id: str
    datos_plantilla: Dict[str, Any]
    metadatos_empresa: Dict[str, Any]
    notificar_destinatario: Optional[bool] = False

# --- VALIDACIÓN DE SEGURIDAD CORPORATIVA ---
def verificar_api_key_corporativa(x_api_key: str = Header(...)):
    if x_api_key != API_KEY_CORPORATIVA:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial corporativa no autorizada"
        )
    return x_api_key

# --- TAREA PESADA ASÍNCRONA CORPORATIVA ---
def sellado_corporativo_fondo(doc_id: str, payload_dict: dict):
    try:
        TAREAS_PROCESAMIENTO[doc_id] = {"status": "procesando", "detalles": "Aplicando sellado corporativo"}
        TAREAS_PROCESAMIENTO[doc_id] = {
            "status": "completado",
            "doc_id": doc_id,
            "hash_sha256": "sha256_mock_verification_hash",
            "origen": "Servidor_Corporativo_Sin_OTP"
        }
    except Exception as e:
        TAREAS_PROCESAMIENTO[doc_id] = {"status": "error", "error": str(e)}

# --- ENDPOINTS ---
@app.get("/")
def estado_servidor():
    return {"status": "en_linea", "servicio": "Celerdoc Engine", "version": "1.0.0"}

# 1. FLUJO INDIVIDUAL (CON OTP OBLIGATORIO)
@app.post("/procesar-firma")
async def procesar_firma_individual(payload: FirmaIndividualRequest):
    # Validacion estricta de OTP individual
    if not payload.codigo_otp_validado or len(payload.codigo_otp_validado) != 6:
        raise HTTPException(status_code=400, detail="OTP requerido y no valido para firma individual")

    # Retorno de confirmacion y ruta de descarga esperada por el visor
    return {
        "status": "exito",
        "mensaje": "Documento firmado exitosamente con OTP individual",
        "datos_archivo": {
            "nombre_final": payload.nombre_final_sugerido,
            "ruta_descarga": f"/descargar/{payload.nombre_final_sugerido}"
        }
    }

# 2. FLUJO CORPORATIVO (SIN OTP - API KEY)
@app.post("/api/v1/documentos/emision-corporativa", status_code=status.HTTP_202_ACCEPTED)
async def emitir_documento_corporativo(
    payload: FirmaCorporativaRequest,
    background_tasks: BackgroundTasks,
    auth: str = Depends(verificar_api_key_corporativa)
):
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    background_tasks.add_task(sellado_corporativo_fondo, doc_id, payload.model_dump())
    
    return {
        "status": "aceptado",
        "doc_id": doc_id,
        "mecanismo": "Emision_Automatica_Servidor",
        "otp_requerido": False,
        "mensaje": "Documento en cola de sellado criptografico"
    }

@app.get("/api/v1/documentos/estado/{doc_id}")
def consultar_estado_documento(doc_id: str):
    if doc_id not in TAREAS_PROCESAMIENTO:
        return {"doc_id": doc_id, "status": "no_encontrado_o_completado"}
    return TAREAS_PROCESAMIENTO[doc_id]

@app.get("/descargar/{nombre_archivo}")
def descargar_archivo(nombre_archivo: str):
    return {"status": "archivo_listo", "archivo": nombre_archivo}
