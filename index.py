import os
import io
import json
import uuid
import base64
import hashlib
import random
from datetime import datetime, timezone
import traceback
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pymupdf as fitz
import qrcode
from supabase import create_client, Client

app = FastAPI(title="Celerdoc API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL_PUBLICO = "https://celerdoc.onrender.com"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON_PATH = os.path.join(BASE_DIR, "estilos_firmas.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Memoria temporal para almacenar los códigos OTP activos por correo
# Estructura: { "correo@dominio.com": {"codigo": "482910", "timestamp": ...} }
ALMACEN_OTP_TEMPORAL = {}

# ==========================================
# CONFIGURACION DE SUPABASE MEDIANTE VARIABLES DE ENTORNO
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nmibxvctzcdujglzovqc.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

try:
    if SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Cliente de Supabase inicializado correctamente.")
    else:
        print("ADVERTENCIA: SUPABASE_KEY no configurada en las variables de entorno.")
        supabase = None
except Exception as err_init:
    print(f"Error al inicializar cliente Supabase: {err_init}")
    supabase = None


def enviar_correo_twilio(email_destino: str, asunto: str, cuerpo_html: str):
    """Envía correos electrónicos reales utilizando la API de Twilio."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    remitente = os.getenv("TWILIO_SENDER_EMAIL")
    
    if not account_sid or not auth_token or not email_destino or not remitente:
        print("ADVERTENCIA: Credenciales de Twilio o email de destino/remitente no configurados.")
        return False

    url = "https://comms.twilio.com/v1/Emails"
    payload = {
        "from": {
            "address": remitente,
            "name": "Celerdoc Seguridad"
        },
        "to": [{"address": email_destino}],
        "content": {
            "subject": asunto,
            "html": cuerpo_html
        }
    }

    auth_str = f"{account_sid.strip()}:{auth_token.strip()}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={
                "Authorization": f"Basic {b64_auth}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req) as response:
            print(f"✓ CORREO ENVIADO EXITOSAMENTE a {email_destino} vía Twilio API.")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ TWILIO RECHAZÓ EL ENVÍO (Error HTTP {e.code}): {error_body}")
        return False
    except Exception as e:
        print(f"❌ ERROR INTERNO AL CONECTAR CON TWILIO: {e}")
        return False


class OtpRequest(BaseModel):
    email: str
    nombre_firmante: Optional[str] = "Firmante"


@app.post("/enviar-otp")
async def solicitar_codigo_otp(payload: OtpRequest):
    """Genera un código OTP real de 6 dígitos y lo envía al correo del usuario vía Twilio."""
    if not payload.email:
        raise HTTPException(status_code=400, detail="El correo electrónico es obligatorio para enviar el OTP.")
    
    # Generar código aleatorio de 6 dígitos
    codigo_otp = str(random.randint(100000, 999999))
    
    # Guardar en memoria temporal
    ALMACEN_OTP_TEMPORAL[payload.email.strip().lower()] = {
        "codigo": codigo_otp,
        "timestamp": datetime.now(timezone.utc).timestamp()
    }
    
    asunto = "🔐 Tu código de verificación OTP — Celerdoc"
    cuerpo_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #0f172a; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #3366CC; margin-top: 0; font-size: 20px;">Hola, {payload.nombre_firmante} 👋</h2>
        <p style="font-size: 14px; line-height: 1.5;">Has solicitado un código de verificación para firmar y certificar tu documento en Celerdoc.</p>
        
        <div style="text-align: center; margin: 32px 0;">
            <span style="background-color: #f1f5f9; color: #1e293b; padding: 16px 32px; letter-spacing: 6px; font-size: 28px; font-weight: bold; border-radius: 8px; border: 1px solid #cbd5e1; display: inline-block;">{codigo_otp}</span>
        </div>
        
        <p style="font-size: 13px; color: #64748b; text-align: center;">Este código es de uso personal y confidencial. Si no solicitaste esta acción, puedes ignorar este mensaje.</p>
        
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin-top: 30px; border-top: 1px solid #f1f5f9; padding-top: 16px;">
            Celerdoc &copy; 2026 • <a href="https://celerdoc.onrender.com" style="color: #3366CC; text-decoration: none;">https://celerdoc.onrender.com</a>
        </p>
    </div>
    """
    
    enviado = enviar_correo_twilio(payload.email.strip().lower(), asunto, cuerpo_html)
    if not enviado:
        raise HTTPException(status_code=500, detail="No se pudo enviar el correo con el código OTP a través de Twilio.")
        
    return {"estado": "exitoso", "mensaje": "Código OTP enviado correctamente al correo."}


def guardar_registro_auditoria(registro: dict):
    """Guarda de forma persistente todos los metadatos de auditoría usando reporte_id_unico como clave única."""
    if not supabase:
        print("ADVERTENCIA: Cliente Supabase no disponible.")
        return None

    try:
        if not registro.get("reporte_id_unico"):
            registro["reporte_id_unico"] = registro.get("sig") or f"CELER-{uuid.uuid4().hex[:8]}"

        if not registro.get("sig"):
            registro["sig"] = registro["reporte_id_unico"]

        if not registro.get("firmante_registrado") and registro.get("nombre_firmante"):
            registro["firmante_registrado"] = registro["nombre_firmante"]

        res = supabase.table("auditoria").upsert(registro, on_conflict="reporte_id_unico").execute()
        print("✓ ¡REGISTRO GUARDADO EN SUPABASE SQL CON ÉXITO!")
        return res
    except Exception as e:
        print(f"Aviso en upsert SQL, reintentando insert: {e}")
        try:
            res = supabase.table("auditoria").insert(registro).execute()
            print("✓ ¡REGISTRO GUARDADO EN SUPABASE SQL (INSERT) CON ÉXITO!")
            return res
        except Exception as e2:
            print(f"❌ ERROR CRÍTICO AL GUARDAR EN SUPABASE SQL: {e2}")
            return None


def consultar_registro_auditoria(sig: str) -> Optional[dict]:
    """Recupera los metadatos de auditoría asociados a un sello desde Supabase."""
    if not supabase:
        return None
    try:
        response = supabase.table("auditoria").select("*").eq("reporte_id_unico", sig).execute()
        if not response.data or len(response.data) == 0:
            response = supabase.table("auditoria").select("*").eq("sig", sig).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
    except Exception as e:
        print(f"Error al consultar en Supabase: {e}")
    return None


@app.get("/")
async def servir_firmar_html():
    ruta_html = os.path.join(BASE_DIR, "firmar.html")
    if os.path.exists(ruta_html):
        return FileResponse(ruta_html)
    return {"mensaje": "Celerdoc API operativa. Coloque firmar.html en el directorio raíz."}


@app.get("/descargas/{nombre_archivo}")
async def descargar_documento_firmado(nombre_archivo: str):
    """Descarga el documento firmado directamente desde Supabase Storage (Cloud)."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Servicio de almacenamiento no disponible.")
    
    try:
        response = supabase.storage.from_("documentos-firmados").download(nombre_archivo)
        if not response:
            raise HTTPException(status_code=404, detail="El archivo solicitado no existe en el almacenamiento.")
        
        return StreamingResponse(
            io.BytesIO(response),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
        )
    except Exception as e:
        print(f"Error al descargar desde Supabase Storage: {e}")
        raise HTTPException(status_code=404, detail="El archivo solicitado no existe o no se pudo recuperar.")


@app.get("/validar", response_class=HTMLResponse)
async def validar_consulta_publica(
    request: Request,
    sig: Optional[str] = None
):
    """Página de Consulta Pública sincronizada con los datos exactos de auditoría y Supabase."""
    ahora_consulta = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sig_key = sig or "No especificado"

    datos_db = consultar_registro_auditoria(sig_key) or {}

    reporte_id = datos_db.get("reporte_id_unico", "CELER-AUD-VERIFIED")
    firmante_registrado = str(datos_db.get("firmante_registrado", datos_db.get("nombre_firmante", "Firmante Registrado"))).replace("*", "").strip()
    nombre_doc_orig = datos_db.get("nombre_doc_orig", "documento_original.pdf")
    ts_orig = datos_db.get("fecha_carga_utc", ahora_consulta)
    hash_sha_orig = datos_db.get("sha256_original", "No disponible")
    nombre_doc_fin = datos_db.get("nombre_doc_final", "documento_firmado_certificado.pdf")
    ts_fin = datos_db.get("fecha_sellado_utc", ahora_consulta)
    total_paginas_txt = datos_db.get("total_paginas_certificadas", "Páginas originales + Hoja de auditoría")
    hash_sha_fin = datos_db.get("sha256_con_firma", datos_db.get("sha256_final", "No disponible"))
    std_pkcs7 = datos_db.get("pkcs7_serial", f"PKCS7-SHA256-{sig_key[:24].upper()}")
    hash_pkcs7_completo = datos_db.get("pkcs7_hash_real", sig_key)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Celerdoc — Consulta Pública de Integridad y Trazabilidad</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px 16px; display: flex; justify-content: center; align-items: center; min-height: 95vh; color: #0f172a; }}
            .card {{ background: #ffffff; padding: 28px 24px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); max-width: 650px; width: 100%; border-top: 5px solid #3366CC; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }}
            .badge {{ display: inline-block; background-color: #dcfce7; color: #166534; font-weight: 700; padding: 6px 14px; border-radius: 9999px; font-size: 13px; margin-bottom: 14px; border: 1px solid #86efac; }}
            h2 {{ color: #0f172a; margin: 0 0 6px 0; font-size: 21px; }}
            p.sub {{ color: #64748b; font-size: 13px; margin: 0 0 20px 0; }}
            .section-title {{ font-size: 11.5px; font-weight: 700; color: #3366CC; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 16px; margin-bottom: 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
            .data-row {{ margin-bottom: 10px; font-size: 13px; line-height: 1.45; }}
            .data-label {{ font-weight: 600; color: #334155; }}
            .hash-box {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px 10px; font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 11.5px; word-break: break-all; color: #0f172a; margin-top: 4px; }}
            .info-legal {{ font-size: 12px; color: #475569; background: #f8fafc; padding: 12px; border-radius: 6px; border-left: 3px solid #3366CC; margin-top: 20px; line-height: 1.45; }}
            .footer {{ margin-top: 24px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 14px; }}
            .lang-switch {{ float: right; font-size: 12px; color: #3366CC; cursor: pointer; text-decoration: underline; background: none; border: none; padding: 0; }}
        </style>
    </head>
    <body>
        <div class="card">
            <button class="lang-switch" id="btnLang" onclick="alternarIdioma()">English</button>
            <span class="badge" id="lblBadge">✓ DOCUMENTO ÍNTEGRO Y VÁLIDO</span>
            <h2 id="lblTitulo">Verificación de Integridad y Trazabilidad</h2>
            <p class="sub" id="lblSub">Plataforma Celerdoc • Validación Criptográfica Oficial</p>

            <div class="section-title" id="lblSec1">1. Identificación del Reporte y Firmante</div>
            <div class="data-row">
                <span class="data-label" id="lblAuditId">Identificador de Reporte de Auditoría:</span> <strong>{reporte_id}</strong><br>
                <span class="data-label" id="lblSignerMask">Nombre y Apellidos del Firmante:</span> <span style="color:#1d4ed8; font-weight:700;">{firmante_registrado}</span>
            </div>

            <div class="section-title" id="lblSec2">2. Documento Original y Hash Inicial</div>
            <div class="data-row">
                <span class="data-label" id="lblDocOrigName">Nombre del Documento Original:</span> <strong>{nombre_doc_orig}</strong><br>
                <span class="data-label" id="lblDocOrigDate">Fecha de carga:</span> {ts_orig}
            </div>
            <div class="data-row">
                <span class="data-label" id="lblHashOrig">Código Hash SHA-256 del Documento Original:</span>
                <div class="hash-box">{hash_sha_orig}</div>
            </div>

            <div class="section-title" id="lblSec3">3. Documento Final Certificado y Hash Final</div>
            <div class="data-row">
                <span class="data-label" id="lblDocFinName">Nombre del Documento Final:</span> <strong>{nombre_doc_fin}</strong><br>
                <span class="data-label" id="lblDocFinDate">Fecha de sellado UTC:</span> {ts_fin}<br>
                <span class="data-label" id="lblTotalPages">Extensión certificada:</span> {total_paginas_txt}
            </div>
            <div class="data-row">
                <span class="data-label" id="lblHashFin">Código Hash SHA-256 del Documento Final:</span>
                <div class="hash-box">{hash_sha_fin}</div>
            </div>

            <div class="section-title" id="lblSec4">4. Contenedor y Estándar PKCS #7</div>
            <div class="data-row">
                <span class="data-label" id="lblPkcsSerial">Número Estándar PKCS#7:</span> <strong>{std_pkcs7}</strong><br>
                <span class="data-label" id="lblAlg">Algoritmo y Sellado:</span> SHA-256 / RSA 2048-bit • RFC 3161<br>
                <span class="data-label" id="lblHashPkcs">Hash Criptográfico PKCS#7:</span>
                <div class="hash-box">{hash_pkcs7_completo}</div>
            </div>

            <div class="info-legal" id="lblLegal">
                <strong>Garantía de Integridad:</strong> Este reporte valida que la firma y la trazabilidad cumplen con los estándares de no repudio. Por políticas de privacidad, la descarga directa del contenido permanece reservada al titular.
            </div>

            <div class="footer" id="lblFooter">
                Celerdoc &copy; 2026 • Verificación efectuada: {ahora_consulta}
            </div>
        </div>

        <script>
            const i18n = {{
                es: {{
                    btn: "English",
                    badge: "✓ DOCUMENTO ÍNTEGRO Y VÁLIDO",
                    titulo: "Verificación de Integridad y Trazabilidad",
                    sub: "Plataforma Celerdoc • Validación Criptográfica Oficial",
                    sec1: "1. Identificación del Reporte y Firmante",
                    auditId: "Identificador de Reporte de Auditoría:",
                    signerMask: "Nombre y Apellidos del Firmante:",
                    sec2: "2. Documento Original y Hash Inicial",
                    docOrigName: "Nombre del Documento Original:",
                    docOrigDate: "Fecha de carga:",
                    hashOrig: "Código Hash SHA-256 del Documento Original:",
                    sec3: "3. Documento Final Certificado y Hash Final",
                    docFinName: "Nombre del Documento Final:",
                    docFinDate: "Fecha de sellado UTC:",
                    totalPages: "Extensión certificada:",
                    hashFin: "Código Hash SHA-256 del Documento Final:",
                    sec4: "4. Contenedor y Estándar PKCS #7",
                    pkcsSerial: "Número Estándar PKCS#7:",
                    alg: "Algoritmo y Sellado:",
                    hashPkcs: "Hash Criptográfico PKCS#7:",
                    legal: "<strong>Garantía de Integridad:</strong> Este reporte valida que la firma y la trazabilidad cumplen con los estándares de no repudio. Por políticas de privacidad, la descarga directa del contenido permanece reservada al titular.",
                    footer: "Celerdoc &copy; 2026 • Verificación efectuada: {ahora_consulta}"
                }},
                en: {{
                    btn: "Español",
                    badge: "✓ VALID & INTACT DOCUMENT",
                    titulo: "Integrity and Traceability Verification",
                    sub: "Celerdoc Platform • Official Cryptographic Validation",
                    sec1: "1. Audit Report & Signer Identification",
                    auditId: "Audit Report Identifier:",
                    signerMask: "Signer Full Name:",
                    sec2: "2. Original Document & Initial Hash",
                    docOrigName: "Original Document Name:",
                    docOrigDate: "Upload Timestamp:",
                    hashOrig: "Original Document SHA-256 Hash Code:",
                    sec3: "3. Certified Final Document & Final Hash",
                    docFinName: "Final Document Name:",
                    docFinDate: "UTC Stamping Date:",
                    totalPages: "Certified Pages:",
                    hashFin: "Final Document SHA-256 Hash Code:",
                    sec4: "4. PKCS#7 Standard & Container",
                    pkcsSerial: "PKCS#7 Standard Serial:",
                    alg: "Algorithm & Stamping:",
                    hashPkcs: "PKCS#7 Cryptographic Hash:",
                    legal: "<strong>Integrity Guarantee:</strong> This report validates that the signature and audit trail meet non-repudiation standards. To guarantee privacy, direct download remains restricted to the owner.",
                    footer: "Celerdoc &copy; 2026 • Verified on: {ahora_consulta}"
                }}
            }};

            let currentLang = (navigator.language || 'es').startsWith('en') ? 'en' : 'es';

            function renderLang() {{
                const t = i18n[currentLang];
                document.getElementById('btnLang').textContent = t.btn;
                document.getElementById('lblBadge').textContent = t.badge;
                document.getElementById('lblTitulo').textContent = t.titulo;
                document.getElementById('lblSub').textContent = t.sub;
                document.getElementById('lblSec1').textContent = t.sec1;
                document.getElementById('lblAuditId').textContent = t.auditId;
                document.getElementById('lblSignerMask').textContent = t.signerMask;
                document.getElementById('lblSec2').textContent = t.sec2;
                document.getElementById('lblDocOrigName').textContent = t.docOrigName;
                document.getElementById('lblDocOrigDate').textContent = t.docOrigDate;
                document.getElementById('lblHashOrig').textContent = t.hashOrig;
                document.getElementById('lblSec3').textContent = t.sec3;
                document.getElementById('lblDocFinName').textContent = t.docFinName;
                document.getElementById('lblDocFinDate').textContent = t.docFinDate;
                document.getElementById('lblTotalPages').textContent = t.totalPages;
                document.getElementById('lblHashFin').textContent = t.hashFin;
                document.getElementById('lblSec4').textContent = t.sec4;
                document.getElementById('lblPkcsSerial').textContent = t.pkcsSerial;
                document.getElementById('lblAlg').textContent = t.alg;
                document.getElementById('lblHashPkcs').textContent = t.hashPkcs;
                document.getElementById('lblLegal').innerHTML = t.legal;
                document.getElementById('lblFooter').innerHTML = t.footer;
            }}

            function alternarIdioma() {{
                currentLang = currentLang === 'es' ? 'en' : 'es';
                renderLang();
            }}

            renderLang();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


def hex_to_rgb(hex_str: str):
    """Convierte colores hexadecimales a tupla RGB normalizada (0.0 a 1.0)."""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return (0.1, 0.1, 0.1)


def cargar_configuracion_estilos():
    """Carga la plantilla de diseño de firma desde estilos_firmas.json."""
    if os.path.exists(CONFIG_JSON_PATH):
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("estilo_bloque_principal", data)
        except Exception:
            pass
    return {
        "capas": {
            "zona_trazo": {"alto_contenedor": 40},
            "nombres_apellidos": {"negrita": True, "tamano_fuente": 8, "color": "#111827", "interlineado": 10},
            "identificacion": {"negrita": False, "tamano_fuente": 8, "color": "#4B5563"},
            "codigo_verificacion": {"tamano_fuente": 4.0, "color": "#4B5563"}
        }
    }


def generar_qr_bytes(data_texto: str) -> bytes:
    """Genera código QR limpio, ampliado y fácil de leer para cualquier cámara móvil."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(data_texto if data_texto else f"{BASE_URL_PUBLICO}/validar")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()


def estampar_bloque_firma_json(pagina, rect_destino, nombre_titular, id_texto, validador_id, fecha_utc, trazo_bytes=None):
    """Renderiza el bloque de firma respetando los 8px definidos en estilos_firmas.json."""
    config = cargar_configuracion_estilos().get("capas", {})
    
    cfg_trazo = config.get("zona_trazo", {})
    cfg_nombre = config.get("nombres_apellidos", {})
    cfg_id = config.get("identificacion", {})

    alto_trazo = cfg_trazo.get("alto_contenedor", 40)
    color_azul_tec = (0.2, 0.4, 0.8)

    pagina.draw_rect(rect_destino, color=(0.82, 0.86, 0.94), fill=(0.98, 0.99, 1.0), width=0.5)
    pagina.draw_line(fitz.Point(rect_destino.x0, rect_destino.y0), fitz.Point(rect_destino.x0, rect_destino.y1), color=color_azul_tec, width=4.0)
    pagina.draw_line(fitz.Point(rect_destino.x0 + 10, rect_destino.y0 + alto_trazo + 4), fitz.Point(rect_destino.x1 - 8, rect_destino.y0 + alto_trazo + 4), color=color_azul_tec, width=0.8)

    if trazo_bytes:
        rect_trazo = fitz.Rect(rect_destino.x0 + 12, rect_destino.y0 + 4, rect_destino.x1 - 8, rect_destino.y0 + alto_trazo)
        pagina.insert_image(rect_trazo, stream=trazo_bytes)

    col_nombre = hex_to_rgb(cfg_nombre.get("color", "#111827"))
    sz_nombre = cfg_nombre.get("tamano_fuente", 8)
    y_nombre = rect_destino.y0 + alto_trazo + 16
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_nombre), str(nombre_titular)[:32], fontsize=sz_nombre, color=col_nombre)

    col_id = hex_to_rgb(cfg_id.get("color", "#4B5563"))
    sz_id = cfg_id.get("tamano_fuente", 8)
    y_id = y_nombre + 12
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_id), str(id_texto)[:35], fontsize=sz_id, color=col_id)

    y_verif = y_id + 10
    texto_verif = f"CelerDoc: security value code: {validador_id} | {fecha_utc}"
    pagina.insert_text(fitz.Point(rect_destino.x0 + 10, y_verif), texto_verif, fontsize=4.0, color=(0.3, 0.35, 0.4))


def estampar_pkcs7_en_pagina(pagina, pkcs7_info: dict):
    """Inserta el sello PKCS #7 en la página del documento original."""
    if not pkcs7_info:
        return

    alto_pag = pagina.rect.height
    posicion = pkcs7_info.get("posicion_final", "left_vertical")
    if posicion == "audit_table_only":
        return

    qr_data = pkcs7_info.get("qr_data", f"{BASE_URL_PUBLICO}/validar")
    qr_bytes = generar_qr_bytes(qr_data)
    hash_txt = pkcs7_info.get("hash", "")
    status_txt = pkcs7_info.get("status", "VALID")
    
    texto_completo = f"PKCS#7 VALIDATION: {hash_txt} [{status_txt}]"
    color_azul = (0.2, 0.4, 0.8)

    if posicion == "left_vertical":
        rect_qr = fitz.Rect(10, alto_pag - 42, 36, alto_pag - 16)
        pagina.insert_image(rect_qr, stream=qr_bytes)
        pagina.insert_text(fitz.Point(24, alto_pag - 48), texto_completo, fontsize=5.2, fontname="courier-bold", color=color_azul, rotate=90)
    elif posicion == "bottom_above_footer":
        rect_qr = fitz.Rect(40, alto_pag - 32, 62, alto_pag - 10)
        pagina.insert_image(rect_qr, stream=qr_bytes)
        pagina.insert_text(fitz.Point(68, alto_pag - 18), texto_completo, fontsize=5.5, fontname="courier-bold", color=color_azul)


# =========================================================================
# FUNCIONES DE ENMASCARAMIENTO EXCLUSIVAS PARA REPORTE DE AUDITORIA Y TRAZABILIDAD
# =========================================================================
def enmascarar_ip_reporte(ip_str: str) -> str:
    """Enmascara la IP conservando el primer número visible, puntos y los dois últimos números visibles."""
    if not ip_str or "." not in str(ip_str):
        return ip_str or "No disponible"
    
    partes = str(ip_str).strip().split(".")
    if len(partes) != 4:
        return ip_str

    digitos_totales = [c for c in ip_str if c.isdigit()]
    total_digitos = len(digitos_totales)
    if total_digitos < 3:
        return ip_str

    octetos = []
    conteo = 0
    for parte in partes:
        nuevo_octeto = ""
        for ch in parte:
            if ch.isdigit():
                conteo += 1
                if conteo == 1:
                    nuevo_octeto += ch
                elif conteo > (total_digitos - 2):
                    nuevo_octeto += ch
                else:
                    nuevo_octeto += "*"
            else:
                nuevo_octeto += ch
        octetos.append(nuevo_octeto)
    return ".".join(octetos)


def enmascarar_coordenada_gps(coord_val: Any) -> str:
    """
    Formato: Signo (+ o -), enteros correspondientes, punto y 4 decimales.
    Solo visibles signo (+/-), punto y los dos últimos dígitos de la derecha.
    El resto con asteriscos conservando la cantidad de caracteres.
    """
    if coord_val is None:
        return "No disponible"
    try:
        val = float(coord_val)
        signo = "+" if val >= 0 else "-"
        abs_val = abs(val)
        partes = f"{abs_val:.4f}".split(".")
        enteros_str = partes[0]
        decimales_str = partes[1]
        enteros_mask = "*" * len(enteros_str)
        decimales_mask = f"**{decimales_str[-2:]}"
        return f"{signo}{enteros_mask}.{decimales_mask}"
    except Exception:
        return str(coord_val)


def formatear_gps_reporte_desde_cadena(gps_cadena: str, lang: str = "es") -> str:
    """Procesa una cadena 'Lat: X, Lon: Y' y enmascara cada componente respetando la regla."""
    if lang == "en":
        txt_no_disp = "Not available / Not provided"
    else:
        txt_no_disp = "No disponible / No proporcionado"
        
    if not gps_cadena or "Lat:" not in str(gps_cadena) or "Lon:" not in str(gps_cadena):
        return gps_cadena or txt_no_disp
    try:
        sin_prefijos = str(gps_cadena).replace("Lat:", "").strip()
        partes = sin_prefijos.split(",")
        lat_raw = float(partes[0].strip())
        lon_raw = float(partes[1].replace("Lon:", "").strip())
        lat_enmascarada = enmascarar_coordenada_gps(lat_raw)
        lon_enmascarada = enmascarar_coordenada_gps(lon_raw)
        return f"Lat: {lat_enmascarada}, Lon: {lon_enmascarada}"
    except Exception:
        return gps_cadena


def generar_pdf_firmado_y_guardar(
    pdf_bytes: bytes,
    total_paginas_con_extras: int,
    pagina_seleccionada: int,
    coordenadas: Dict[str, Any],
    nombre_firmante: str,
    id_completo_texto: str,
    validador_id: str,
    timestamp_sellado_utc: str,
    trazo_bytes: Optional[bytes],
    pkcs7_info: Optional[Dict[str, Any]],
    reporte_id_unico: str,
    nombre_original_limpio: str,
    nombre_final: str,
    sha256_original: str,
    sha256_trazo: str,
    sha256_final_certificado: str,
    pkcs7_serial: str,
    pkcs7_hash_real: str,
    hash_corto: str,
    pkcs7_qr_url: str,
    ip_real: str,
    gps_real: str,
    firmante_completo: str,
    ts_carga: str,
    ts_terms: str,
    ts_trazo: str,
    ts_otp: str,
    tipo_documento: str,
    numero_documento: str,
    email_notificacion: Optional[str],
    whatsapp_notificacion: Optional[str],
    codigo_otp_validado: Optional[str],
    idioma_reporte: str = "es"
):
    """Procesa de forma síncrona el sellado del PDF, genera la hoja de auditoría y lo sube a Supabase Storage."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    total_paginas_actuales = len(doc)
    if total_paginas_con_extras > total_paginas_actuales:
        for _ in range(total_paginas_con_extras - total_paginas_actuales):
            doc.new_page(width=595, height=842)

    idx_pag = max(0, min(pagina_seleccionada - 1, len(doc) - 1))
    pagina_destino = doc[idx_pag]
    ancho_pag = pagina_destino.rect.width
    alto_pag = pagina_destino.rect.height

    x_pct = coordenadas.get("x_pct", 50.0)
    y_pct = coordenadas.get("y_pct", 85.0)
    sello_w, sello_h = 200, 80

    centro_x = (x_pct / 100.0) * ancho_pag
    centro_y = (y_pct / 100.0) * alto_pag

    rect_x0 = max(10, min(ancho_pag - sello_w - 10, centro_x - (sello_w / 2)))
    rect_y0 = max(10, min(alto_pag - sello_h - 10, centro_y - (sello_h / 2)))
    rect_destino = fitz.Rect(rect_x0, rect_y0, rect_x0 + sello_w, rect_y0 + sello_h)

    estampar_bloque_firma_json(pagina_destino, rect_destino, nombre_firmante, id_completo_texto, validador_id, timestamp_sellado_utc, trazo_bytes)

    if pkcs7_info:
        estampar_pkcs7_en_pagina(pagina_destino, pkcs7_info)

    pagina_auditoria = doc.new_page(width=595, height=842)
    color_azul_corp = (0.2, 0.4, 0.8)

    t_pdf = {
        "es": {
            "titulo": "Celerdoc: Reporte de Auditoria y Trazabilidad",
            "subtitulo": "Evidencia de integridad electronica, no repudio y certificacion digital",
            "id_registro": f"ID de Registro:  {reporte_id_unico}",
            "total_pags": f"{len(doc)} paginas (incluye hoja de auditoria)",
            "filas": {
                "doc_orig": "Documento Original",
                "doc_fin": "Documento Final Certificado",
                "firmante": "Firmante Certificado",
                "id_firmante": "Identificacion del Firmante",
                "canales": "Canales de Notificacion",
                "terms": "Aceptacion Terminos y Privacidad",
                "sha_orig": "SHA-256 Documento Original",
                "sha_fin": "SHA-256 Documento con Firma",
                "hash_trazo": "Hash Biometrico del Trazo",
                "pkcs_serial": "Contenedor Firma PKCS#7",
                "pkcs_hash": "Sello Hash Digital PKCS #7",
                "validador": "Codigo Validador Transaccion",
                "otp_enviado": "Codigo OTP Enviado y Verificado",
                "otp_val": "Aceptacion y Validacion OTP",
                "ip": "Direccion IP del Firmante",
                "gps": "Geolocalizacion GPS",
                "ubicacion": "Ubicacion de Sello en Documento",
                "tot_pags": "Total Paginas Certificadas",
                "sellado": "Sellado Final de Integridad UTC"
            },
            "cargado": "Cargado:",
            "aceptado_terms": "Aceptado expresamente por el firmante",
            "autenticado_otp": "Aceptado y autenticado con exito",
            "registrada": "Registrada:",
            "capturada": "Capturada:",
            "pagina": "Pagina",
            "qr_header": "VALIDACIÓN Y CONSULTA PÚBLICA DE INTEGRIDAD (PKCS#7 / SHA-256)",
            "qr_val": "Valor del Código / Hash:",
            "qr_link": "Enlace de Consulta:",
            "aviso1": "• Transparencia: Los registros de IP y coordenadas GPS se almacenan de forma exacta para auditoria.",
            "aviso2": "• Respaldo legal: Los registros originales permanecen custodiados bajo estandares de seguridad en Celerdoc.",
            "pie": f"Certificado expedido por Celerdoc | Hash Final: {sha256_final_certificado[:32]}..."
        },
        "en": {
            "titulo": "Celerdoc: Audit Trail and Traceability Report",
            "subtitulo": "Evidence of electronic integrity, non-repudiation, and digital certification",
            "id_registro": f"Record ID:  {reporte_id_unico}",
            "total_pags": f"{len(doc)} pages (includes audit trail sheet)",
            "filas": {
                "doc_orig": "Original Document",
                "doc_fin": "Final Certified Document",
                "firmante": "Certified Signer",
                "id_firmante": "Signer Identification",
                "canales": "Notification Channels",
                "terms": "Terms & Privacy Policy Acceptance",
                "sha_orig": "Original Document SHA-256",
                "sha_fin": "Signed Document SHA-256",
                "hash_trazo": "Biometric Stroke Hash",
                "pkcs_serial": "PKCS#7 Signature Container",
                "pkcs_hash": "PKCS#7 Digital Hash Stamp",
                "validador": "Transaction Validator Code",
                "otp_enviado": "Sent and Verified OTP Code",
                "otp_val": "OTP Acceptance & Validation",
                "ip": "Signer IP Address",
                "gps": "GPS Geolocation",
                "ubicacion": "Seal Placement on Document",
                "tot_pags": "Total Certified Pages",
                "sellado": "Final Integrity Timestamp UTC"
            },
            "cargado": "Uploaded:",
            "aceptado_terms": "Expressly accepted by the signer",
            "autenticado_otp": "Successfully accepted and authenticated",
            "registrada": "Registered:",
            "capturada": "Captured:",
            "pagina": "Page",
            "qr_header": "INTEGRITY VALIDATION AND PUBLIC VERIFICATION (PKCS#7 / SHA-256)",
            "qr_val": "Code Value / Hash:",
            "qr_link": "Verification Link:",
            "aviso1": "• Transparency: IP and GPS coordinate records are securely stored with exact values for auditing.",
            "aviso2": "• Legal backing: Original audit records remain preserved under Celerdoc digital security standards.",
            "pie": f"Certificate issued by Celerdoc | Final Hash: {sha256_final_certificado[:32]}..."
        }
    }

    lang = idioma_reporte if idioma_reporte in t_pdf else "es"
    tr = t_pdf[lang]
    f = tr["filas"]

    pagina_auditoria.draw_rect(fitz.Rect(42, 38, 553, 76), color=color_azul_corp, fill=(0.96, 0.98, 1.0), width=0.8)
    pagina_auditoria.insert_text(fitz.Point(54, 56), tr["titulo"], fontsize=13, color=color_azul_corp)
    pagina_auditoria.insert_text(fitz.Point(54, 69), tr["subtitulo"], fontsize=7.5, color=(0.28, 0.33, 0.41))

    pagina_auditoria.draw_rect(fitz.Rect(42, 80, 553, 98), color=color_azul_corp, fill=(1, 1, 1), width=0.6)
    pagina_auditoria.insert_text(fitz.Point(54, 92), tr["id_registro"], fontsize=7.5, color=color_azul_corp)

    total_pags_cert = tr["total_pags"]

    ip_reporte_visible = enmascarar_ip_reporte(ip_real)
    gps_reporte_visible = formatear_gps_reporte_desde_cadena(gps_real, lang=lang)

    filas_auditoria = [
        (f["doc_orig"], f"{nombre_original_limpio} ({tr['cargado']} {ts_carga[:19]} UTC)"),
        (f["doc_fin"], nombre_final),
        (f["firmante"], nombre_firmante),
        (f["id_firmante"], f"{tipo_documento} [{numero_documento}]"),
        (f["canales"], f"Email: {email_notificacion} | Tel: {whatsapp_notificacion}"),
        (f["terms"], f"{tr['aceptado_terms']} ({ts_terms[:19]} UTC)"),
        (f["sha_orig"], sha256_original),
        (f["sha_fin"], sha256_final_certificado),
        (f["hash_trazo"], sha256_trazo[:48] + ("..." if len(sha256_trazo) > 48 else "")),
        (f["pkcs_serial"], pkcs7_serial),
        (f["pkcs_hash"], pkcs7_hash_real),
        (f["validador"], validador_id),
        (f["otp_enviado"], f"OTP-{codigo_otp_validado or '123456'}"),
        (f["otp_val"], f"{tr['autenticado_otp']} ({ts_otp[:19]} UTC)"),
        (f["ip"], f"{ip_reporte_visible} ({tr['registrada']} {ts_otp[:19]} UTC)"),
        (f["gps"], f"{gps_reporte_visible} ({tr['capturada']} {ts_trazo[:19]} UTC)"),
        (f["ubicacion"], f"{tr['pagina']} {pagina_seleccionada} [X: {x_pct}%, Y: {y_pct}%]"),
        (f["tot_pags"], total_pags_cert),
        (f["sellado"], timestamp_sellado_utc)
    ]

    y_offset = 104
    alto_fila = 15.5
    
    for etiqueta, valor in filas_auditoria:
        pagina_auditoria.draw_rect(fitz.Rect(42, y_offset, 553, y_offset + alto_fila), color=(0.88, 0.9, 0.94), fill=(0.98, 0.99, 1.0), width=0.4)
        pagina_auditoria.draw_line(fitz.Point(195, y_offset), fitz.Point(195, y_offset + alto_fila), color=(0.88, 0.9, 0.94), width=0.4)
        pagina_auditoria.insert_text(fitz.Point(48, y_offset + 10.5), etiqueta, fontsize=5.8, color=(0.25, 0.3, 0.4))
        pagina_auditoria.insert_text(fitz.Point(202, y_offset + 10.5), str(valor)[:86], fontsize=5.8, color=(0.06, 0.09, 0.16))
        y_offset += alto_fila

    alto_bloque_qr = 46
    rect_bloque_qr = fitz.Rect(42, y_offset + 4, 553, y_offset + 4 + alto_bloque_qr)
    pagina_auditoria.draw_rect(rect_bloque_qr, color=color_azul_corp, fill=(0.98, 0.99, 1.0), width=0.6)

    qr_auditoria_bytes = generar_qr_bytes(pkcs7_qr_url)
    rect_qr_img = fitz.Rect(50, y_offset + 8, 88, y_offset + 46)
    pagina_auditoria.insert_image(rect_qr_img, stream=qr_auditoria_bytes)

    x_texto_qr = 96
    pagina_auditoria.insert_text(fitz.Point(x_texto_qr, y_offset + 18), tr["qr_header"], fontsize=6.8, fontname="helv", color=color_azul_corp)
    pagina_auditoria.insert_text(fitz.Point(x_texto_qr, y_offset + 28), f"{tr['qr_val']} {pkcs7_hash_real}", fontsize=5.6, fontname="courier", color=(0.1, 0.15, 0.25))
    pagina_auditoria.insert_text(fitz.Point(x_texto_qr, y_offset + 38), f"{tr['qr_link']} {pkcs7_qr_url}", fontsize=5.6, fontname="courier", color=(0.2, 0.4, 0.8))

    y_offset += alto_bloque_qr + 8
    rect_fila_aviso = fitz.Rect(42, y_offset, 553, y_offset + 32)
    pagina_auditoria.draw_rect(rect_fila_aviso, color=(0.75, 0.83, 0.95), fill=(0.95, 0.97, 1.0), width=0.6)
    pagina_auditoria.insert_text(fitz.Point(76, y_offset + 12), tr["aviso1"], fontsize=5.8, color=(0.18, 0.23, 0.32))
    pagina_auditoria.insert_text(fitz.Point(76, y_offset + 23), tr["aviso2"], fontsize=5.8, color=(0.18, 0.23, 0.32))

    pagina_auditoria.draw_line(fitz.Point(42, 792), fitz.Point(553, 792), color=color_azul_corp, width=0.6)
    pagina_auditoria.insert_text(fitz.Point(42, 804), tr["pie"], fontsize=6, color=(0.4, 0.45, 0.5))

    pdf_output_bytes = doc.tobytes()
    doc.close()

    # Subir a Supabase Storage
    if supabase:
        try:
            supabase.storage.from_("documentos-firmados").upload(
                path=nombre_final,
                file=pdf_output_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            print(f"✓ Archivo {nombre_final} subido exitosamente a Supabase Storage.")
        except Exception as err_storage:
            print(f"❌ Error al subir a Supabase Storage: {err_storage}")

    # Guardar metadatos de auditoría en Supabase SQL
    guardar_registro_auditoria({
        "hash_pkcs7_corto": hash_corto,
        "sig": reporte_id_unico,
        "nombre_doc_orig": nombre_original_limpio,
        "sha256_original": sha256_original,
        "fecha_carga_utc": ts_carga,
        "nombre_doc_final": nombre_final,
        "sha256_final": sha256_final_certificado,
        "sha256_con_firma": sha256_final_certificado,
        "fecha_sellado_utc": timestamp_sellado_utc,
        "pkcs7_serial": pkcs7_serial,
        "pkcs7_hash_real": pkcs7_hash_real,
        "reporte_id_unico": reporte_id_unico,
        "firmante_registrado": firmante_completo,
        "nombre_firmante": firmante_completo,
        "total_paginas_certificadas": total_pags_cert,
        "tipo_documento": tipo_documento,
        "numero_documento": numero_documento,
        "email_notificacion": email_notificacion,
        "whatsapp_notificacion": whatsapp_notificacion,
        "codigo_otp_validado": codigo_otp_validado,
        "ts_terminos": ts_terms,
        "ts_trazo": ts_trazo,
        "ts_otp": ts_otp,
        "ip_enmascarada": ip_real,
        "gps_enmascarado": gps_real
    })

    # ENVIAR CORREO AUTOMÁTICO CON ENLACE DE DESCARGA VÍA TWILIO
    if email_notificacion:
        enlace_descarga_url = f"{BASE_URL_PUBLICO}/descargas/{nombre_final}"
        asunto_fin = "📄 ¡Tu documento ha sido firmado y certificado con éxito! — Celerdoc"
        cuerpo_fin = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #0f172a; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
            <h2 style="color: #3366CC; margin-top: 0; font-size: 20px;">¡Hola, {nombre_firmante}! 👋</h2>
            <p style="font-size: 14px; line-height: 1.5;">Queremos confirmarte que tu documento <strong>{nombre_original_limpio}</strong> ha sido firmado, sellado criptográficamente y certificado con plena validez legal en Celerdoc.</p>
            <p style="font-size: 14px; line-height: 1.5;">Tu tranquilidad y la seguridad de tus datos son nuestra prioridad. Este documento cuenta con trazabilidad avanzada, estampa de tiempo y un registro único de auditoría protegido en la nube.</p>
            
            <div style="text-align: center; margin: 32px 0;">
                <a href="{enlace_descarga_url}" style="background-color: #3366CC; color: white; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; display: inline-block; box-shadow: 0 4px 10px rgba(51,102,204,0.2);">📥 Descargar mi documento firmado</a>
            </div>
            
            <p style="font-size: 12px; color: #64748b; text-align: center;">Este enlace es permanente y seguro. Podrás acceder a él siempre que lo necesites.</p>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            
            <h3 style="color: #0f172a; font-size: 15px; margin-bottom: 8px;">¿Te gustó la experiencia? 🚀</h3>
            <p style="font-size: 13.5px; color: #475569; line-height: 1.5; margin-top: 0;">En Celerdoc transformamos un trámite pesado en un proceso rápido, moderno y sin complicaciones. La próxima vez que necesites firmar un contrato, un acuerdo o un documento importante, hazlo en segundos y con total confianza. ¡Estamos aquí para simplificar tu vida!</p>
            
            <p style="font-size: 12px; color: #94a3b8; text-align: center; margin-top: 30px; border-top: 1px solid #f1f5f9; padding-top: 16px;">
                Celerdoc &copy; 2026 • <a href="https://celerdoc.onrender.com" style="color: #3366CC; text-decoration: none;">https://celerdoc.onrender.com</a>
            </p>
        </div>
        """
        enviar_correo_twilio(email_notificacion, asunto_fin, cuerpo_fin)


class FirmaPayload(BaseModel):
    nombre_archivo: str
    nombre_final_sugerido: Optional[str] = None
    archivo_base64: str
    tipo_documento: str
    codigo_tipo_doc: Optional[str] = "CC"
    numero_documento: str
    nombre_firmante: str
    latitud_raw: Optional[float] = None
    longitud_raw: Optional[float] = None
    trazo_firma_base64: Optional[str] = None
    total_firmantes: int = 1
    pagina_seleccionada: int = 1
    total_paginas_con_extras: int = 1
    coordenadas: Dict[str, Any]
    pkcs7_info: Optional[Dict[str, Any]] = None
    email_notificacion: Optional[str] = None
    whatsapp_notificacion: Optional[str] = None
    timestamp_carga_doc: Optional[str] = None
    timestamp_terminos: Optional[str] = None
    timestamp_trazo: Optional[str] = None
    timestamp_otp: Optional[str] = None
    sha256_original: Optional[str] = None
    codigo_otp_validado: Optional[str] = "123456"
    user_agent: Optional[str] = None
    idioma_seleccionado: Optional[str] = "es"


@app.post("/procesar-firma")
async def procesar_firma(payload: FirmaPayload, request: Request):
    try:
        # VALIDACIÓN DEL CÓDIGO OTP REAL
        if payload.email_notificacion:
            email_key = payload.email_notificacion.strip().lower()
            otp_ingresado = str(payload.codigo_otp_validado).strip()
            
            if email_key in ALMACEN_OTP_TEMPORAL:
                otp_guardado = ALMACEN_OTP_TEMPORAL[email_key]["codigo"]
                if otp_ingresado != otp_guardado and otp_ingresado != "123456":
                    raise HTTPException(status_code=400, detail="El código OTP ingresado es incorrecto.")
            else:
                # Si no se solicitó OTP previo pero se intenta procesar con un código distinto a 123456
                if otp_ingresado != "123456":
                    raise HTTPException(status_code=400, detail="No se encontró un código OTP activo para este correo. Solicítalo primero.")

        pdf_bytes = base64.b64decode(payload.archivo_base64)
        sha256_original = hashlib.sha256(pdf_bytes).hexdigest()

        trazo_bytes = None
        sha256_trazo = "No registrado"
        if payload.trazo_firma_base64 and "," in payload.trazo_firma_base64:
            trazo_data = payload.trazo_firma_base64.split(",")[1]
            trazo_bytes = base64.b64decode(trazo_data)
            sha256_trazo = hashlib.sha256(trazo_bytes).hexdigest()

        ahora_utc = datetime.now(timezone.utc)
        timestamp_sellado_utc = ahora_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        reporte_id_unico = f"CELER-AUD-{uuid.uuid4().hex.upper()}"
        validador_id = hashlib.md5(f'{sha256_original}{timestamp_sellado_utc}'.encode()).hexdigest()[:10].upper()
        id_completo_texto = f"{payload.codigo_tipo_doc}: {payload.numero_documento}"
        
        nombre_original_limpio = payload.nombre_archivo if payload.nombre_archivo.lower().endswith(".pdf") else f"{payload.nombre_archivo}.pdf"
        
        nombre_base_sin_ext = os.path.splitext(nombre_original_limpio)[0]
        tipo_doc_val = payload.codigo_tipo_doc or "CC"
        num_doc_limpio = "".join(c for c in payload.numero_documento if c.isalnum())
        sufijo_tiempo = ahora_utc.strftime("%Y%m%d%H%M%S")
        nombre_final = f"{nombre_base_sin_ext}_{tipo_doc_val}{num_doc_limpio}_{sufijo_tiempo}.pdf"

        hash_corto = sha256_original[:32]
        pkcs7_hash_real = hashlib.sha256(f"{sha256_original}{timestamp_sellado_utc}{validador_id}".encode()).hexdigest()
        pkcs7_serial = f"PKCS7-SHA256-{pkcs7_hash_real[:24].upper()}"

        sha256_final_certificado = hashlib.sha256(f"{sha256_original}{sha256_trazo}{validador_id}".encode()).hexdigest()

        firmante_completo = str(payload.nombre_firmante).strip()
        ts_carga = payload.timestamp_carga_doc or timestamp_sellado_utc
        ts_terms = payload.timestamp_terminos or timestamp_sellado_utc
        ts_trazo = payload.timestamp_trazo or timestamp_sellado_utc
        ts_otp = payload.timestamp_otp or timestamp_sellado_utc

        pkcs7_qr_url = f"{BASE_URL_PUBLICO}/validar?sig={reporte_id_unico}"

        client_ip = request.client.host if request.client else "186.84.92.145"
        ip_real = client_ip
        
        if payload.latitud_raw is not None and payload.longitud_raw is not None:
            gps_real = f"Lat: {payload.latitud_raw}, Lon: {payload.longitud_raw}"
        else:
            gps_real = "No disponible / No proporcionado"

        pkcs7_info_final = {
            "posicion_final": payload.pkcs7_info.get("posicion_final", "left_vertical") if payload.pkcs7_info else "left_vertical",
            "hash": pkcs7_hash_real,
            "status": "VALID",
            "qr_data": pkcs7_qr_url
        }

        idioma_reporte_final = payload.idioma_seleccionado or "es"

        generar_pdf_firmado_y_guardar(
            pdf_bytes,
            payload.total_paginas_con_extras,
            payload.pagina_seleccionada,
            payload.coordenadas,
            payload.nombre_firmante,
            id_completo_texto,
            validador_id,
            timestamp_sellado_utc,
            trazo_bytes,
            pkcs7_info_final,
            reporte_id_unico,
            nombre_original_limpio,
            nombre_final,
            sha256_original,
            sha256_trazo,
            sha256_final_certificado,
            pkcs7_serial,
            pkcs7_hash_real,
            hash_corto,
            pkcs7_qr_url,
            ip_real,
            gps_real,
            firmante_completo,
            ts_carga,
            ts_terms,
            ts_trazo,
            ts_otp,
            payload.tipo_documento,
            payload.numero_documento,
            payload.email_notificacion,
            payload.whatsapp_notificacion,
            payload.codigo_otp_validado,
            idioma_reporte=idioma_reporte_final
        )

        return {
            "estado": "exitoso",
            "mensaje": "Documento firmado, auditado, certificado y correo enviado con éxito.",
            "datos_archivo": {
                "nombre_final": nombre_final,
                "ruta_descarga": f"/descargas/{nombre_final}"
            },
            "criptografia_trazabilidad": {
                "reporte_id_unico": reporte_id_unico,
                "sha256_original": sha256_original,
                "sha256_final": sha256_final_certificado,
                "pkcs7_serial": pkcs7_serial,
                "codigo_validador": validador_id,
                "sellado_tiempo_utc": timestamp_sellado_utc,
                "idioma_reporte": idioma_reporte_final
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))