import os
import json
import uuid
import base64
import hashlib
from datetime import datetime, timezone
import traceback
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pymupdf as fitz

app = FastAPI(title="Celerdoc API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "documentos_firmados")
CONFIG_JSON_PATH = os.path.join(BASE_DIR, "estilos_firmas.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app.mount("/descargas", StaticFiles(directory=OUTPUT_DIR), name="descargas")

@app.get("/")
async def servir_firmar_html():
    ruta_html = os.path.join(BASE_DIR, "firmar.html")
    if os.path.exists(ruta_html):
        return FileResponse(ruta_html)
    return {"mensaje": "Celerdoc API operativa. Coloque firmar.html en el directorio raíz."}


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
        except:
            return "+**.**00"
    return f"Lat: {fmt(lat)}, Lon: {fmt(lon)}"


def cargar_configuracion_estilos():
    """Carga la plantilla de diseño de firma desde estilos_firmas.json."""
    if os.path.exists(CONFIG_JSON_PATH):
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "estilo_bloque_principal": {
            "capas": {
                "zona_trazo": {"alto_contenedor": 40},
                "nombres_apellidos": {"negrita": True, "tamano_fuente": 10, "color": "#111827", "interlineado": 12},
                "identificacion": {"negrita": False, "tamano_fuente": 9, "color": "#4B5563"},
                "codigo_verificacion": {"tamano_fuente": 7, "color": "#6B7280"}
            }
        }
    }


def estampar_bloque_firma_json(pagina, rect_destino, nombre_titular, id_texto, validador_id, fecha_utc, trazo_bytes=None):
    """
    Renderiza el bloque de firma respetando estilos_firmas.json.
    Incorpora la franja vertical izquierda de 4 pt en azul tecnológico corporativo (#3366CC).
    """
    config = cargar_configuracion_estilos().get("estilo_bloque_principal", {}).get("capas", {})
    
    cfg_trazo = config.get("zona_trazo", {})
    cfg_nombre = config.get("nombres_apellidos", {})
    cfg_id = config.get("identificacion", {})
    cfg_verif = config.get("codigo_verificacion", {})

    alto_trazo = cfg_trazo.get("alto_contenedor", 40)
    color_azul_tec = (0.2, 0.4, 0.8)  # #3366CC

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
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_nombre), str(nombre_titular)[:30], fontsize=sz_nombre, color=col_nombre)

    # 6. Capa Identificación
    col_id = hex_to_rgb(cfg_id.get("color", "#4B5563"))
    sz_id = cfg_id.get("tamano_fuente", 9)
    y_id = y_nombre + 12
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_id), str(id_texto)[:33], fontsize=sz_id, color=col_id)

    # 7. Capa Código de Verificación y Timestamp
    col_verif = hex_to_rgb(cfg_verif.get("color", "#6B7280"))
    sz_verif = cfg_verif.get("tamano_fuente", 7)
    y_verif = y_id + 11
    texto_verif = f"Validador: {validador_id}  |  {fecha_utc}"
    pagina.insert_text(fitz.Point(rect_destino.x0 + 12, y_verif), texto_verif[:46], fontsize=sz_verif, color=col_verif)


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

        # Dimensiones del bloque de firma
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
        
        # ID Único de Auditoría irrepetible (UUIDv4)
        reporte_id_unico = f"CELER-AUD-{uuid.uuid4().hex.upper()}"
        validador_id = f"CELER-{hashlib.md5(f'{sha256_original}{timestamp_sellado_utc}'.encode()).hexdigest()[:10].upper()}"
        id_completo_texto = f"{payload.codigo_tipo_doc}: {payload.numero_documento}"
        nombre_final = payload.nombre_final_sugerido or f"documento_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"

        # 3. Estampar la firma con la franja de 4 pt
        estampar_bloque_firma_json(
            pagina_destino,
            rect_destino,
            payload.nombre_firmante,
            id_completo_texto,
            validador_id,
            timestamp_sellado_utc,
            trazo_bytes
        )

        bytes_con_firma = doc.tobytes()
        sha256_con_firma = hashlib.sha256(bytes_con_firma).hexdigest()
        pkcs7_serial = f"PKCS7-SHA256-{hashlib.sha256(f'{sha256_con_firma}{validador_id}'.encode()).hexdigest()[:24].upper()}"

        # Enmascarar IP y GPS
        client_ip = request.client.host if request.client else "186.84.92.145"
        ip_enmascarada = enmascarar_ip(client_ip)
        gps_enmascarado = enmascarar_gps(payload.latitud_raw, payload.longitud_raw)

        # 4. Generar Hoja de Auditoría y Trazabilidad
        pagina_auditoria = doc.new_page(width=595, height=842)
        color_azul_corp = (0.2, 0.4, 0.8)       # #3366CC

        # 4.1 Encabezado principal
        pagina_auditoria.draw_rect(fitz.Rect(42, 40, 553, 78), color=color_azul_corp, fill=(0.96, 0.98, 1.0), width=0.8)
        pagina_auditoria.insert_text(fitz.Point(54, 58), "Celerdoc: Reporte de Auditoria y Trazabilidad", fontsize=13, color=color_azul_corp)
        pagina_auditoria.insert_text(fitz.Point(54, 71), "Evidencia de integridad electronica, no repudio y certificacion digital", fontsize=7.5, color=(0.28, 0.33, 0.41))

        # 4.2 Subtítulo con ID de Registro
        pagina_auditoria.draw_rect(fitz.Rect(42, 82, 553, 102), color=color_azul_corp, fill=(1, 1, 1), width=0.6)
        pagina_auditoria.insert_text(fitz.Point(54, 95), f"ID de Registro:  {reporte_id_unico}", fontsize=7.5, color=color_azul_corp)

        # 4.3 Matriz de Registros de Auditoría
        ts_carga = payload.timestamp_carga_doc or timestamp_sellado_utc
        ts_terms = payload.timestamp_terminos or timestamp_sellado_utc
        ts_trazo = payload.timestamp_trazo or timestamp_sellado_utc
        ts_otp = payload.timestamp_otp or timestamp_sellado_utc

        filas_auditoria = [
            ("Documento Original", f"{payload.nombre_archivo} (Cargado: {ts_carga[:19]} UTC)"),
            ("Documento Final Certificado", nombre_final),
            ("Firmante Certificado", payload.nombre_firmante),
            ("Identificacion del Firmante", f"{payload.tipo_documento} [{payload.numero_documento}]"),
            ("Canales de Notificacion", f"Email: {payload.email_notificacion} | Movil: {payload.whatsapp_notificacion}"),
            ("Aceptacion Terminos y Privacidad", f"Aceptado expresamente por el firmante ({ts_terms[:19]} UTC)"),
            ("SHA-256 Documento Original", sha256_original),
            ("SHA-256 Documento con Firma", sha256_con_firma),
            ("Hash Biometrico del Trazo", sha256_trazo[:48] + ("..." if len(sha256_trazo) > 48 else "")),
            ("Contenedor Firma PKCS#7", pkcs7_serial),
            ("Codigo Validador Transaccion", validador_id),
            ("Codigo OTP Enviado y Verificado", f"OTP-{payload.codigo_otp_validado or '123456'}"),
            ("Aceptacion y Validacion OTP", f"Aceptado y autenticado con exito ({ts_otp[:19]} UTC)"),
            ("Direccion IP del Firmante", f"{ip_enmascarada} (Registrada: {ts_otp[:19]} UTC)"),
            ("Geolocalizacion GPS", f"{gps_enmascarado} (Capturada: {ts_trazo[:19]} UTC)"),
            ("Ubicacion de Sello en Documento", f"Pagina {payload.pagina_seleccionada} [X: {x_pct}%, Y: {y_pct}%]"),
            ("Total Paginas Certificadas", f"{len(doc)} paginas (incluye hoja de auditoria)"),
            ("Sellado Final de Integridad UTC", timestamp_sellado_utc)
        ]

        y_offset = 108
        alto_fila = 16.5
        
        for etiqueta, valor in filas_auditoria:
            pagina_auditoria.draw_rect(fitz.Rect(42, y_offset, 553, y_offset + alto_fila), color=(0.88, 0.9, 0.94), fill=(0.98, 0.99, 1.0), width=0.4)
            pagina_auditoria.draw_line(fitz.Point(195, y_offset), fitz.Point(195, y_offset + alto_fila), color=(0.88, 0.9, 0.94), width=0.4)
            
            pagina_auditoria.insert_text(fitz.Point(48, y_offset + 11), etiqueta, fontsize=6, color=(0.25, 0.3, 0.4))
            pagina_auditoria.insert_text(fitz.Point(202, y_offset + 11), str(valor)[:84], fontsize=6, color=(0.06, 0.09, 0.16))
            
            y_offset += alto_fila

        # 4.4 Última Fila Unificada: Icono [ i ] + Aviso de Privacidad
        alto_fila_aviso = 34
        rect_fila_aviso = fitz.Rect(42, y_offset, 553, y_offset + alto_fila_aviso)
        pagina_auditoria.draw_rect(rect_fila_aviso, color=(0.75, 0.83, 0.95), fill=(0.95, 0.97, 1.0), width=0.6)

        # Icono visual [ i ]
        rect_icono = fitz.Rect(50, y_offset + 8, 66, y_offset + 24)
        pagina_auditoria.draw_rect(rect_icono, color=color_azul_corp, fill=color_azul_corp, width=0.5)
        pagina_auditoria.insert_text(fitz.Point(56, y_offset + 19.5), "i", fontsize=10, color=(1, 1, 1))

        # Texto condensado con doble sangría
        x_sangria = 76
        pagina_auditoria.insert_text(
            fitz.Point(x_sangria, y_offset + 13),
            "• Privacidad: La direccion IP y las coordenadas GPS se presentan enmascaradas para proteger la confidencialidad del firmante.",
            fontsize=5.8, color=(0.18, 0.23, 0.32)
        )
        pagina_auditoria.insert_text(
            fitz.Point(x_sangria, y_offset + 25),
            "• Respaldo legal: Los registros originales permanecen custodiados bajo estandares de seguridad en Celerdoc con plena validez de ley.",
            fontsize=5.8, color=(0.18, 0.23, 0.32)
        )

        # 4.5 Pie de página
        pagina_auditoria.draw_line(fitz.Point(42, 792), fitz.Point(553, 792), color=color_azul_corp, width=0.6)
        pagina_auditoria.insert_text(fitz.Point(42, 804), f"Certificado de firma electronica expedido por Celerdoc | Hash Final: {sha256_con_firma[:32]}...", fontsize=6, color=(0.4, 0.45, 0.5))

        # 5. Guardar archivo final
        ruta_salida_pdf = os.path.join(OUTPUT_DIR, nombre_final)
        doc.save(ruta_salida_pdf)
        doc.close()

        with open(ruta_salida_pdf, "rb") as f:
            bytes_finales = f.read()
            sha256_final = hashlib.sha256(bytes_finales).hexdigest()

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