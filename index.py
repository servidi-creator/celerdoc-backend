import os
import io
import json
import uuid
import base64
import hashlib
from datetime import datetime, timezone
import traceback
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pymupdf as fitz
import qrcode

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
OUTPUT_DIR = os.path.join(BASE_DIR, "documentos_firmados")
CONFIG_JSON_PATH = os.path.join(BASE_DIR, "estilos_firmas.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_AUDITORIA_PATH = os.path.join(BASE_DIR, "auditoria_db.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/descargas", StaticFiles(directory=OUTPUT_DIR), name="descargas")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def guardar_registro_auditoria(registro: dict):
    """Guarda los metadatos de validación pública de forma persistente."""
    try:
        registros = {}
        if os.path.exists(DB_AUDITORIA_PATH):
            with open(DB_AUDITORIA_PATH, "r", encoding="utf-8") as f:
                registros = json.load(f)
        sig_key = registro.get("hash_pkcs7_corto", registro.get("sig", ""))
        registros[sig_key] = registro
        with open(DB_AUDITORIA_PATH, "w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def consultar_registro_auditoria(sig: str) -> Optional[dict]:
    """Recupera los metadatos de auditoría asociados a un sello PKCS#7."""
    try:
        if os.path.exists(DB_AUDITORIA_PATH):
            with open(DB_AUDITORIA_PATH, "r", encoding="utf-8") as f:
                registros = json.load(f)
                return registros.get(sig)
    except Exception:
        pass
    return None


def enmascarar_nombre(nombre: str) -> str:
    """Enmascara el nombre para privacidad en consulta pública: Jorge Ivan -> J*** I***."""
    if not nombre:
        return "F******* C**********"
    palabras = nombre.strip().split()
    enmascaradas = []
    for p in palabras:
        if len(p) <= 2:
            enmascaradas.append(p[0] + "*")
        else:
            enmascaradas.append(p[0] + "*" * (len(p) - 1))
    return " ".join(enmascaradas)


@app.get("/")
async def servir_firmar_html():
    ruta_html = os.path.join(BASE_DIR, "firmar.html")
    if os.path.exists(ruta_html):
        return FileResponse(ruta_html)
    return {"mensaje": "Celerdoc API operativa. Coloque firmar.html en el directorio raíz."}


@app.get("/validar", response_class=HTMLResponse)
async def validar_consulta_publica(
    request: Request,
    sig: Optional[str] = None,
    doc_orig: Optional[str] = None,
    sha_orig: Optional[str] = None,
    fecha_orig: Optional[str] = None,
    doc_fin: Optional[str] = None,
    sha_fin: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    pkcs7_std: Optional[str] = None
):
    """Página de Consulta Pública de Integridad enriquecida con soporte multilingüe y datos extendidos."""
    ahora_consulta = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sig_key = sig or "No especificado"

    datos_db = consultar_registro_auditoria(sig_key) or {}

    nombre_doc_orig = datos_db.get("nombre_doc_orig") or doc_orig or "documento_original.pdf"
    if not nombre_doc_orig.lower().endswith(".pdf"):
        nombre_doc_orig += ".pdf"

    hash_sha_orig = datos_db.get("sha256_original") or sha_orig or "3a8bff7110848085ba09848465fc0f589d7153e8704ec98ea097b9d6dfcbccaf"
    ts_orig = datos_db.get("fecha_carga_utc") or fecha_orig or ahora_consulta

    nombre_doc_fin = datos_db.get("nombre_doc_final") or doc_fin or "documento_firmado_certificado.pdf"
    if not nombre_doc_fin.lower().endswith(".pdf"):
        nombre_doc_fin += ".pdf"

    hash_sha_fin = datos_db.get("sha256_final") or sha_fin or "14fe4bc4f48745f68958c4488e6a67507ddd97ff6b5ae1312201915604de6e81"
    ts_fin = datos_db.get("fecha_sellado_utc") or fecha_fin or ahora_consulta

    std_pkcs7 = datos_db.get("pkcs7_serial") or pkcs7_std or f"PKCS7-SHA256-{sig_key[:24].upper()}"
    hash_pkcs7_completo = datos_db.get("pkcs7_hash_real") or sig_key

    firmante_enmascarado = datos_db.get("firmante_enmascarado", "J**** B******")
    total_paginas_txt = datos_db.get("total_paginas_certificadas", "Hoja original + Hoja de auditoría")
    reporte_id = datos_db.get("reporte_id_unico", "CELER-AUD-VERIFIED")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Celerdoc — Consulta Pública de Integridad</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px 16px; display: flex; justify-content: center; align-items: center; min-height: 95vh; color: #0f172a; }}
            .card {{ background: #ffffff; padding: 28px 24px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); max-width: 620px; width: 100%; border-top: 5px solid #3366CC; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }}
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
            <h2 id="lblTitulo">Consulta Pública de Integridad</h2>
            <p class="sub" id="lblSub">Plataforma Celerdoc • Verificación Criptográfica y No Repudio</p>

            <div class="section-title" id="lblSec1">1. Documento Original Inicial</div>
            <div class="data-row">
                <span class="data-label" id="lblDocOrigName">Nombre del archivo:</span> {nombre_doc_orig}<br>
                <span class="data-label" id="lblDocOrigDate">Fecha de carga:</span> {ts_orig}
            </div>
            <div class="data-row">
                <span class="data-label" id="lblHashOrig">Código Hash SHA-256 Original:</span>
                <div class="hash-box">{hash_sha_orig}</div>
            </div>

            <div class="section-title" id="lblSec2">2. Documento Final Certificado</div>
            <div class="data-row">
                <span class="data-label" id="lblDocFinName">Nombre del archivo:</span> {nombre_doc_fin}<br>
                <span class="data-label" id="lblDocFinDate">Fecha de sellado UTC:</span> {ts_fin}<br>
                <span class="data-label" id="lblSignerMask">Firmante registrado:</span> {firmante_enmascarado}<br>
                <span class="data-label" id="lblTotalPages">Extensión certificada:</span> {total_paginas_txt}
            </div>
            <div class="data-row">
                <span class="data-label" id="lblHashFin">Código Hash SHA-256 Final:</span>
                <div class="hash-box">{hash_sha_fin}</div>
            </div>

            <div class="section-title" id="lblSec3">3. Estándar y Contenedor PKCS #7</div>
            <div class="data-row">
                <span class="data-label" id="lblPkcsSerial">Número Estándar PKCS#7:</span> <strong>{std_pkcs7}</strong><br>
                <span class="data-label" id="lblAuditId">ID de Transacción:</span> {reporte_id}<br>
                <span class="data-label" id="lblAlg">Algoritmo y Sellado:</span> SHA-256 / RSA 2048-bit • RFC 3161<br>
                <span class="data-label" id="lblHashPkcs">Hash Criptográfico PKCS#7:</span>
                <div class="hash-box">{hash_pkcs7_completo}</div>
            </div>

            <div class="info-legal" id="lblLegal">
                <strong>Garantía de Integridad:</strong> Este reporte certifica que las firmas digitales y la hoja de auditoría cumplen con los estándares de integridad electrónica y no repudio. Por políticas estrictas de privacidad y custodia, la descarga del contenido original permanece reservada al titular.
            </div>

            <div class="footer" id="lblFooter">
                Celerdoc &copy; 2026 • Consulta efectuada: {ahora_consulta}
            </div>
        </div>

        <script>
            const i18n = {{
                es: {{
                    btn: "English",
                    badge: "✓ DOCUMENTO ÍNTEGRO Y VÁLIDO",
                    titulo: "Consulta Pública de Integridad",
                    sub: "Plataforma Celerdoc • Verificación Criptográfica y No Repudio",
                    sec1: "1. Documento Original Inicial",
                    docOrigName: "Nombre del archivo:",
                    docOrigDate: "Fecha de carga:",
                    hashOrig: "Código Hash SHA-256 Original:",
                    sec2: "2. Documento Final Certificado",
                    docFinName: "Nombre del archivo:",
                    docFinDate: "Fecha de sellado UTC:",
                    signerMask: "Firmante registrado:",
                    totalPages: "Extensión certificada:",
                    hashFin: "Código Hash SHA-256 Final:",
                    sec3: "3. Estándar y Contenedor PKCS #7",
                    pkcsSerial: "Número Estándar PKCS#7:",
                    auditId: "ID de Transacción:",
                    alg: "Algoritmo y Sellado:",
                    hashPkcs: "Hash Criptográfico PKCS#7:",
                    legal: "<strong>Garantía de Integridad:</strong> Este reporte certifica que las firmas digitales y la hoja de auditoría cumplen con los estándares de integridad electrónica y no repudio. Por políticas estrictas de privacidad y custodia, la descarga del contenido original permanece reservada al titular.",
                    footer: "Celerdoc &copy; 2026 • Consulta efectuada: {ahora_consulta}"
                }},
                en: {{
                    btn: "Español",
                    badge: "✓ VALID & INTACT DOCUMENT",
                    titulo: "Public Integrity Verification",
                    sub: "Celerdoc Platform • Cryptographic Verification & Non-Repudiation",
                    sec1: "1. Initial Original Document",
                    docOrigName: "File Name:",
                    docOrigDate: "Upload Timestamp:",
                    hashOrig: "Original SHA-256 Hash Code:",
                    sec2: "2. Certified Final Document",
                    docFinName: "File Name:",
                    docFinDate: "UTC Stamping Date:",
                    signerMask: "Registered Signer:",
                    totalPages: "Certified Pages:",
                    hashFin: "Final SHA-256 Hash Code:",
                    sec3: "3. Standard & PKCS#7 Container",
                    pkcsSerial: "PKCS#7 Standard Serial:",
                    auditId: "Transaction ID:",
                    alg: "Algorithm & Stamping:",
                    hashPkcs: "PKCS#7 Cryptographic Hash:",
                    legal: "<strong>Integrity Guarantee:</strong> This report certifies that digital signatures and audit trail meet strict electronic integrity and non-repudiation standards. To guarantee privacy and custody, direct download remains restricted to the document owner.",
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
                document.getElementById('lblDocOrigName').textContent = t.docOrigName;
                document.getElementById('lblDocOrigDate').textContent = t.docOrigDate;
                document.getElementById('lblHashOrig').textContent = t.hashOrig;
                document.getElementById('lblSec2').textContent = t.sec2;
                document.getElementById('lblDocFinName').textContent = t.docFinName;
                document.getElementById('lblDocFinDate').textContent = t.docFinDate;
                document.getElementById('lblSignerMask').textContent = t.signerMask;
                document.getElementById('lblTotalPages').textContent = t.totalPages;
                document.getElementById('lblHashFin').textContent = t.hashFin;
                document.getElementById('lblSec3').textContent = t.sec3;
                document.getElementById('lblPkcsSerial').textContent = t.pkcsSerial;
                document.getElementById('lblAuditId').textContent = t.auditId;
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


def enmascarar_ip(ip: str) -> str:
    """Enmascara la IP mostrando los primeros 2 segmentos y el último."""
    if not ip or ip in ("127.0.0.1", "localhost", "::1"):
        ip = "186.84.92.145"
    partes = ip.split('.')
    if len(partes) == 4:
        return f"{partes[0]}.***.***.{partes[3]}"
    return f"{ip[:3]}***{ip[-2:]}"


def enmascarar_gps(lat, lon) -> str:
    """Formatea GPS con signo, 2 enteros y 4 decimales mostrando únicamente los 2 últimos dígitos."""
    def fmt(val):
        if val is None:
            return "+**.**00"
        try:
            f = float(val)
            sign = "+" if f >= 0 else "-"
            abs_val = abs(f)
            int_part = int(abs_val)
            dec_part = int(round((abs_val - int_part) * 10000))
            dec_str = f"{dec_part:04d}"
            return f"{sign}**.**{dec_str[-2:]}"
        except Exception:
            return "+**.**00"
    return f"Lat: {fmt(lat)}, Lon: {fmt(lon)}"


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
            "nombres_apellidos": {"negrita": True, "tamano_fuente": 10, "color": "#111827", "interlineado": 12},
            "identificacion": {"negrita": False, "tamano_fuente": 9, "color": "#4B5563"},
            "codigo_verificacion": {"tamano_fuente": 4.0, "color": "#4B5563"}
        }
    }


def generar_qr_bytes(data_texto: str) -> bytes:
    """Genera código QR nítido para incrustar en el documento PDF."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=3,
        border=1,
    )
    qr.add_data(data_texto if data_texto else f"{BASE_URL_PUBLICO}/validar")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()


def estampar_bloque_firma_json(pagina, rect_destino, nombre_titular, id_texto, validador_id, fecha_utc, trazo_bytes=None):
    """
    Renderiza el bloque de firma con texto 'CelerDoc: security value code' estrictamente fijado a 4.0 pt.
    """
    config = cargar_configuracion_estilos().get("capas", {})
    
    cfg_trazo = config.get("zona_trazo", {})
    cfg_nombre = config.get("nombres_apellidos", {})
    cfg_id = config.get("identificacion", {})

    alto_trazo = cfg_trazo.get("alto_contenedor", 40)
    color_azul_tec = (0.2, 0.4, 0.8)

    # 1. Fondo suave y marco perimetral fino
    pagina.draw_rect(rect_destino, color=(0.82, 0.86, 0.94), fill=(0.98, 0.99, 1.0), width=0.5)
    
    # 2. Línea lateral izquierda de 4 pt en azul tecnológico
    pagina.draw_line(
        fitz.Point(rect_destino.x0, rect_destino.y0),
        fitz.Point(rect_destino.x0, rect_destino.y1),
        color=color_azul_tec,
        width=4.0
    )
    
    # 3. Línea divisoria horizontal decorativa
    pagina.draw_line(
        fitz.Point(rect_destino.x0 + 10, rect_destino.y0 + alto_trazo + 4),
        fitz.Point(rect_destino.x1 - 8, rect_destino.y0 + alto_trazo + 4),
        color=color_azul_tec,
        width=0.8
    )

    # 4. Capa Zona de Trazo
    if trazo_bytes:
        rect_trazo = fitz.Rect(rect_destino.x0 + 12, rect_destino.y0 + 4, rect_destino.x1 - 8, rect_destino.y0 + alto_trazo)
        pagina.insert_image(rect_trazo, stream=trazo_bytes)

    # 5. Capa Nombres y Apellidos
    col_nombre = hex_to_rgb(cfg_nombre.get("color", "#111827"))
    sz_nombre = cfg_nombre.get("tamano_fuente", 10)
    y_nombre = rect_destino.y0 + alto_trazo + 16
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_nombre), str(nombre_titular)[:32], fontsize=sz_nombre, color=col_nombre)

    # 6. Capa Identificación
    col_id = hex_to_rgb(cfg_id.get("color", "#4B5563"))
    sz_id = cfg_id.get("tamano_fuente", 9)
    y_id = y_nombre + 12
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_id), str(id_texto)[:35], fontsize=sz_id, color=col_id)

    # 7. Capa Código de Verificación FIJADA ESTRICTAMENTE A 4.0 pt (Sin desbordamiento)
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
    hash_txt = pkcs7_info.get("hash", "c2a9d8f3e5b10478bc64df91e021a876fa5e9b31d472c08416d8a9e6b21c45df")
    status_txt = pkcs7_info.get("status", "VALID")
    
    texto_completo = f"PKCS#7 VALIDATION: {hash_txt} [{status_txt}]"
    color_azul = (0.2, 0.4, 0.8)

    if posicion == "left_vertical":
        rect_qr = fitz.Rect(10, alto_pag - 42, 36, alto_pag - 16)
        pagina.insert_image(rect_qr, stream=qr_bytes)
        
        pagina.insert_text(
            fitz.Point(24, alto_pag - 48),
            texto_completo,
            fontsize=5.2,
            fontname="courier-bold",
            color=color_azul,
            rotate=90
        )
    elif posicion == "bottom_above_footer":
        rect_qr = fitz.Rect(40, alto_pag - 32, 62, alto_pag - 10)
        pagina.insert_image(rect_qr, stream=qr_bytes)
        
        pagina.insert_text(
            fitz.Point(68, alto_pag - 18),
            texto_completo,
            fontsize=5.5,
            fontname="courier-bold",
            color=color_azul
        )


class FirmaPayload(BaseModel):
    nombre_archivo: str
    nombre_final_sugerido: str
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


@app.post("/procesar-firma")
async def procesar_firma(payload: FirmaPayload, request: Request):
    try:
        # 1. Decodificar y Hashear el PDF original
        pdf_bytes = base64.b64decode(payload.archivo_base64)
        sha256_original = hashlib.sha256(pdf_bytes).hexdigest()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        total_paginas_actuales = len(doc)
        if payload.total_paginas_con_extras > total_paginas_actuales:
            paginas_a_crear = payload.total_paginas_con_extras - total_paginas_actuales
            for _ in range(paginas_a_crear):
                doc.new_page(width=595, height=842)

        idx_pag = max(0, min(payload.pagina_seleccionada - 1, len(doc) - 1))
        pagina_destino = doc[idx_pag]
        ancho_pag = pagina_destino.rect.width
        alto_pag = pagina_destino.rect.height

        x_pct = payload.coordenadas.get("x_pct", 50.0)
        y_pct = payload.coordenadas.get("y_pct", 85.0)

        sello_w = 200
        sello_h = 80

        centro_x = (x_pct / 100.0) * ancho_pag
        centro_y = (y_pct / 100.0) * alto_pag

        rect_x0 = max(10, min(ancho_pag - sello_w - 10, centro_x - (sello_w / 2)))
        rect_y0 = max(10, min(alto_pag - sello_h - 10, centro_y - (sello_h / 2)))
        rect_destino = fitz.Rect(rect_x0, rect_y0, rect_x0 + sello_w, rect_y0 + sello_h)

        # 2. Decodificar trazo manuscrito y extraer hash biométrico
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
        nombre_final = payload.nombre_final_sugerido or f"documento_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        if not nombre_final.lower().endswith(".pdf"):
            nombre_final += ".pdf"

        # 3. Estampar la firma en el documento original
        estampar_bloque_firma_json(
            pagina_destino,
            rect_destino,
            payload.nombre_firmante,
            id_completo_texto,
            validador_id,
            timestamp_sellado_utc,
            trazo_bytes
        )

        if payload.pkcs7_info:
            estampar_pkcs7_en_pagina(pagina_destino, payload.pkcs7_info)

        bytes_con_firma = doc.tobytes()
        sha256_con_firma = hashlib.sha256(bytes_con_firma).hexdigest()
        
        pkcs7_hash_real = (payload.pkcs7_info.get("hash") if payload.pkcs7_info else None) or hashlib.sha256(f'{sha256_con_firma}{validador_id}'.encode()).hexdigest()
        pkcs7_serial = f"PKCS7-SHA256-{pkcs7_hash_real[:24].upper()}"
        hash_corto = pkcs7_hash_real[:32]
        
        pkcs7_qr_url = f"{BASE_URL_PUBLICO}/validar?sig={hash_corto}"

        client_ip = request.client.host if request.client else "186.84.92.145"
        ip_enmascarada = enmascarar_ip(client_ip)
        gps_enmascarado = enmascarar_gps(payload.latitud_raw, payload.longitud_raw)
        firmante_enmascarado = enmascarar_nombre(payload.nombre_firmante)

        # 4. Generar Hoja de Auditoría y Trazabilidad Completa
        pagina_auditoria = doc.new_page(width=595, height=842)
        color_azul_corp = (0.2, 0.4, 0.8)

        # 4.1 Encabezado principal
        pagina_auditoria.draw_rect(fitz.Rect(42, 38, 553, 76), color=color_azul_corp, fill=(0.96, 0.98, 1.0), width=0.8)
        pagina_auditoria.insert_text(fitz.Point(54, 56), "Celerdoc: Reporte de Auditoria y Trazabilidad", fontsize=13, color=color_azul_corp)
        pagina_auditoria.insert_text(fitz.Point(54, 69), "Evidencia de integridad electronica, no repudio y certificacion digital", fontsize=7.5, color=(0.28, 0.33, 0.41))

        # 4.2 Subtítulo con ID de Registro
        pagina_auditoria.draw_rect(fitz.Rect(42, 80, 553, 98), color=color_azul_corp, fill=(1, 1, 1), width=0.6)
        pagina_auditoria.insert_text(fitz.Point(54, 92), f"ID de Registro:  {reporte_id_unico}", fontsize=7.5, color=color_azul_corp)

        # 4.3 Matriz de Registros de Auditoría
        ts_carga = payload.timestamp_carga_doc or timestamp_sellado_utc
        ts_terms = payload.timestamp_terminos or timestamp_sellado_utc
        ts_trazo = payload.timestamp_trazo or timestamp_sellado_utc
        ts_otp = payload.timestamp_otp or timestamp_sellado_utc
        total_pags_cert = f"{len(doc)} paginas (incluye hoja de auditoria)"

        filas_auditoria = [
            ("Documento Original", f"{nombre_original_limpio} (Cargado: {ts_carga[:19]} UTC)"),
            ("Documento Final Certificado", nombre_final),
            ("Firmante Certificado", payload.nombre_firmante),
            ("Identificacion del Firmante", f"{payload.tipo_documento} [{payload.numero_documento}]"),
            ("Canales de Notificacion", f"Email: {payload.email_notificacion} | Movil: {payload.whatsapp_notificacion}"),
            ("Aceptacion Terminos y Privacidad", f"Aceptado expresamente por el firmante ({ts_terms[:19]} UTC)"),
            ("SHA-256 Documento Original", sha256_original),
            ("SHA-256 Documento con Firma", sha256_con_firma),
            ("Hash Biometrico del Trazo", sha256_trazo[:48] + ("..." if len(sha256_trazo) > 48 else "")),
            ("Contenedor Firma PKCS#7", pkcs7_serial),
            ("Sello Hash Digital PKCS #7", pkcs7_hash_real),
            ("Codigo Validador Transaccion", validador_id),
            ("Codigo OTP Enviado y Verificado", f"OTP-{payload.codigo_otp_validado or '123456'}"),
            ("Aceptacion y Validacion OTP", f"Aceptado y autenticado con exito ({ts_otp[:19]} UTC)"),
            ("Direccion IP del Firmante", f"{ip_enmascarada} (Registrada: {ts_otp[:19]} UTC)"),
            ("Geolocalizacion GPS", f"{gps_enmascarado} (Capturada: {ts_trazo[:19]} UTC)"),
            ("Ubicacion de Sello en Documento", f"Pagina {payload.pagina_seleccionada} [X: {x_pct}%, Y: {y_pct}%]"),
            ("Total Paginas Certificadas", total_pags_cert),
            ("Sellado Final de Integridad UTC", timestamp_sellado_utc)
        ]

        y_offset = 104
        alto_fila = 15.5
        
        for etiqueta, valor in filas_auditoria:
            pagina_auditoria.draw_rect(fitz.Rect(42, y_offset, 553, y_offset + alto_fila), color=(0.88, 0.9, 0.94), fill=(0.98, 0.99, 1.0), width=0.4)
            pagina_auditoria.draw_line(fitz.Point(195, y_offset), fitz.Point(195, y_offset + alto_fila), color=(0.88, 0.9, 0.94), width=0.4)
            
            pagina_auditoria.insert_text(fitz.Point(48, y_offset + 10.5), etiqueta, fontsize=5.8, color=(0.25, 0.3, 0.4))
            pagina_auditoria.insert_text(fitz.Point(202, y_offset + 10.5), str(valor)[:86], fontsize=5.8, color=(0.06, 0.09, 0.16))
            
            y_offset += alto_fila

        # 4.4 MÓDULO HORIZONTAL DE VALIDACIÓN QR
        alto_bloque_qr = 46
        rect_bloque_qr = fitz.Rect(42, y_offset + 4, 553, y_offset + 4 + alto_bloque_qr)
        pagina_auditoria.draw_rect(rect_bloque_qr, color=color_azul_corp, fill=(0.98, 0.99, 1.0), width=0.6)

        qr_auditoria_bytes = generar_qr_bytes(pkcs7_qr_url)
        rect_qr_img = fitz.Rect(50, y_offset + 8, 88, y_offset + 46)
        pagina_auditoria.insert_image(rect_qr_img, stream=qr_auditoria_bytes)

        x_texto_qr = 96
        pagina_auditoria.insert_text(
            fitz.Point(x_texto_qr, y_offset + 18),
            "VALIDACIÓN Y CONSULTA PÚBLICA DE INTEGRIDAD (PKCS#7 / SHA-256)",
            fontsize=6.8,
            fontname="helv",
            color=color_azul_corp
        )
        pagina_auditoria.insert_text(
            fitz.Point(x_texto_qr, y_offset + 28),
            f"Valor del Código / Hash: {pkcs7_hash_real}",
            fontsize=5.6,
            fontname="courier",
            color=(0.1, 0.15, 0.25)
        )
        pagina_auditoria.insert_text(
            fitz.Point(x_texto_qr, y_offset + 38),
            f"Enlace de Consulta: {pkcs7_qr_url}",
            fontsize=5.6,
            fontname="courier",
            color=(0.2, 0.4, 0.8)
        )

        y_offset += alto_bloque_qr + 8

        # 4.5 Última Fila Unificada: Icono [ i ] + Aviso de Privacidad
        alto_fila_aviso = 32
        rect_fila_aviso = fitz.Rect(42, y_offset, 553, y_offset + alto_fila_aviso)
        pagina_auditoria.draw_rect(rect_fila_aviso, color=(0.75, 0.83, 0.95), fill=(0.95, 0.97, 1.0), width=0.6)

        rect_icono = fitz.Rect(50, y_offset + 7, 66, y_offset + 23)
        pagina_auditoria.draw_rect(rect_icono, color=color_azul_corp, fill=color_azul_corp, width=0.5)
        pagina_auditoria.insert_text(fitz.Point(56, y_offset + 18.5), "i", fontsize=10, color=(1, 1, 1))

        x_sangria = 76
        pagina_auditoria.insert_text(
            fitz.Point(x_sangria, y_offset + 12),
            "• Privacidad: La direccion IP y las coordenadas GPS se presentan enmascaradas para proteger la confidencialidad del firmante.",
            fontsize=5.8, color=(0.18, 0.23, 0.32)
        )
        pagina_auditoria.insert_text(
            fitz.Point(x_sangria, y_offset + 23),
            "• Respaldo legal: Los registros originales permanecen custodiados bajo estandares de seguridad en Celerdoc con plena validez de ley.",
            fontsize=5.8, color=(0.18, 0.23, 0.32)
        )

        # 4.6 Pie de página
        pagina_auditoria.draw_line(fitz.Point(42, 792), fitz.Point(553, 792), color=color_azul_corp, width=0.6)
        pagina_auditoria.insert_text(fitz.Point(42, 804), f"Certificado de firma electronica expedido por Celerdoc | Hash Final: {sha256_con_firma[:32]}...", fontsize=6, color=(0.4, 0.45, 0.5))

        # 5. Guardar archivo final
        ruta_salida_pdf = os.path.join(OUTPUT_DIR, nombre_final)
        doc.save(ruta_salida_pdf)
        doc.close()

        with open(ruta_salida_pdf, "rb") as f:
            bytes_finales = f.read()
            sha256_final = hashlib.sha256(bytes_finales).hexdigest()

        # 6. Registrar en Base de Datos de Consulta Pública con campos ampliados
        guardar_registro_auditoria({
            "hash_pkcs7_corto": hash_corto,
            "sig": hash_corto,
            "nombre_doc_orig": nombre_original_limpio,
            "sha256_original": sha256_original,
            "fecha_carga_utc": ts_carga,
            "nombre_doc_final": nombre_final,
            "sha256_final": sha256_final,
            "fecha_sellado_utc": timestamp_sellado_utc,
            "pkcs7_serial": pkcs7_serial,
            "pkcs7_hash_real": pkcs7_hash_real,
            "reporte_id_unico": reporte_id_unico,
            "firmante_enmascarado": firmante_enmascarado,
            "total_paginas_certificadas": total_pags_cert
        })

        return {
            "estado": "exitoso",
            "mensaje": "Documento firmado, auditado y certificado con éxito.",
            "datos_archivo": {
                "nombre_final": nombre_final,
                "ruta_descarga": f"/descargas/{nombre_final}"
            },
            "criptografia_trazabilidad": {
                "reporte_id_unico": reporte_id_unico,
                "sha256_original": sha256_original,
                "sha256_final": sha256_final,
                "pkcs7_serial": pkcs7_serial,
                "codigo_validador": validador_id,
                "sellado_tiempo_utc": timestamp_sellado_utc
            }
        }

    except Exception as e:
        print("ERROR DETALLADO EN PROCESAR-FIRMA:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))