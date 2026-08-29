import os
import json
import base64
import tempfile
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from PIL import Image as PILImage

def generar_apariencia_firma(
    trazo_base64: str,
    nombres: str,
    identificacion: str,
    codigo_verificacion: str,
    output_stream: BytesIO,
    fecha_hora: str = None
) -> None:
    if not fecha_hora:
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ancho = 220
    alto = 100
    radio = 5  # Esquinas redondeadas al 5%

    c = canvas.Canvas(output_stream, pagesize=(ancho, alto))

    # 1. Fondo blanco con esquinas redondeadas
    c.setFillColor(HexColor("#FFFFFF"))
    c.roundRect(1, 1, ancho - 2, alto - 2, radius=radio, stroke=0, fill=1)

    # 2. Borde perimetral azul ultrafino
    c.setStrokeColor(HexColor("#1E40AF"))
    c.setLineWidth(0.3)
    c.roundRect(1, 1, ancho - 2, alto - 2, radius=radio, stroke=1, fill=0)

    # 3. Trazo Biométrico
    alto_trazo = 34
    if trazo_base64:
        if "base64," in trazo_base64:
            base64_data = trazo_base64.split("base64,")[1]
        else:
            base64_data = trazo_base64

        imagen_bytes = base64.b64decode(base64_data)
        img_pil = PILImage.open(BytesIO(imagen_bytes))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
            img_pil.save(temp_img, format="PNG")
            temp_img_path = temp_img.name

        try:
            c.drawImage(
                temp_img_path,
                x=12,
                y=alto - alto_trazo - 6,
                width=ancho - 24,
                height=alto_trazo,
                preserveAspectRatio=True,
                mask="auto"
            )
        finally:
            if os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass

    # 4. Línea divisoria muy suave bajo el trazo
    c.setStrokeColor(HexColor("#E2E8F0"))
    c.setLineWidth(0.3)
    c.line(12, alto - alto_trazo - 8, ancho - 12, alto - alto_trazo - 8)

    # 5. Nombre del Firmante
    y_pos = alto - alto_trazo - 19
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(HexColor("#0F172A"))
    c.drawString(12, y_pos, nombres[:38])

    # 6. Documento de Identidad
    y_pos -= 11
    c.setFont("Helvetica", 7.5)
    c.setFillColor(HexColor("#475569"))
    c.drawString(12, y_pos, identificacion)

    # 7. Trazabilidad CelerDoc (Fecha e ID de Verificación)
    y_pos -= 10
    c.setFont("Helvetica", 6)
    c.setFillColor(HexColor("#64748B"))
    c.drawString(12, y_pos, f"Fecha: {fecha_hora}")

    y_pos -= 8
    hash_formateado = codigo_verificacion[:28] if len(codigo_verificacion) > 28 else codigo_verificacion
    c.drawString(12, y_pos, f"ID Verif: {hash_formateado}")

    c.save()
