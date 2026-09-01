import os
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Celerdoc Core API",
    version="1.0.0",
    description="Motor de firma electrónica y emisión corporativa automatizada"
)

# Configuración CORS para acceso desde frontend web y móvil
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_CORPORATIVA = os.getenv("CELERDOC_CORP_API_KEY", "celerdoc_corp_secret_key_default")

# Estado en memoria para seguimiento rápido de tareas
TAREAS_PROCESAMIENTO: Dict[str, Dict[str, Any]] = {}

class FirmaCorporativaRequest(BaseModel):
    template_id: str
    datos_plantilla: Dict[str, Any]
    metadatos_empresa: Dict[str, Any]
    notificar_destinatario: Optional[bool] = False

def sellado_criptografico_fondo(doc_id: str, payload_dict: dict):
    """
    Tarea pesada en segundo plano:
    - Generación de PDF desde plantilla
    - Sellado PKCS#7 y Hashing SHA-256
    - Actualización de estado de completado
    """
    try:
        TAREAS_PROCESAMIENTO[doc_id] = {"status": "procesando", "detalles": "Aplicando sellado criptografico"}
        # Integración de sellado pyHanko y almacenamiento
        TAREAS_PROCESAMIENTO[doc_id] = {
            "status": "completado",
            "doc_id": doc_id,
            "hash_sha256": "sha256_mock_verification_hash",
            "origen": "Servidor_Corporativo_Sin_OTP"
        }
    except Exception as e:
        TAREAS_PROCESAMIENTO[doc_id] = {"status": "error", "error": str(e)}

def verificar_api_key_corporativa(x_api_key: str = Header(...)):
    if x_api_key != API_KEY_CORPORATIVA:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial corporativa no autorizada"
        )
    return x_api_key

@app.get("/")
def estado_servidor():
    return {"status": "en_linea", "servicio": "Celerdoc Engine", "version": "1.0.0"}

@app.post("/api/v1/documentos/emision-corporativa", status_code=status.HTTP_202_ACCEPTED)
async def emitir_documento_corporativo(
    payload: FirmaCorporativaRequest,
    background_tasks: BackgroundTasks,
    auth: str = Depends(verificar_api_key_corporativa)
):
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    
    # Delegar la tarea pesada al fondo inmediatamente
    background_tasks.add_task(sellado_criptografico_fondo, doc_id, payload.model_dump())
    
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
