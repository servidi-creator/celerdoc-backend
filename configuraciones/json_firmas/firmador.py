import os
import json
import base64
import tempfile
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from PIL import Image as PILImage

def generar_apariencia_firma(
    trazo_base64: str,
    nombres: str,
    identificacion: str,
    codigo_verificacion: str,
    output_stream: BytesIO
) -> None:
    """
    Genera el bloque visual de firma de 4 niveles sobre un canvas temporal 
    para ser inyectado en pyHanko.
    """
    # Cargar configuraciones JSON desde la misma carpeta de forma segura
    with open(os.path.join(os.path.dirname(__file__), "estilos_firmas.json"), 'r', encoding='utf-8') as f:
        estilos = json.load(f)["estilo_bloque_principal"]["capas"]
    
    with open(os.path.join(os.path.dirname(__file__), "configuracion_firmado_pdf.json"), 'r', encoding='utf-8') as f:
        config = json.load(f)["bloque_firma"]

    ancho = config["ancho"]
    alto = config["alto"]
    
    # Crear lienzo con ReportLab
    c = canvas.Canvas(output_stream, pagesize=(ancho, alto))
    
    # 1. Zona de Trazo Biométrico
    if trazo_base64:
        if "base64," in trazo_base64:
            base64_data = trazo_base64.split("base64,")[1]
        else:
            base64_data = trazo_base64
        
        imagen_bytes = base64.b64decode(base64_data)
        img_pil = PILImage.open(BytesIO(imagen_bytes))
        
        # Guardar en un archivo temporal físico para que ReportLab pueda procesar la ruta sin errores de BytesIO
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
            img_pil.save(temp_img, format="PNG")
            temp_img_path = temp_img.name
        
        try:
            c.drawImage(
                temp_img_path, 
                x=10, 
                y=alto - estilos["zona_trazo"]["alto_contenedor"] - 5, 
                width=ancho - 20, 
                height=estilos["zona_trazo"]["alto_contenedor"], 
                preserveAspectRatio=True, 
                mask='auto'
            )
        finally:
            if os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except:
                    pass

    # Coordenadas base iniciales para los textos
    y_base = alto - estilos["zona_trazo"]["alto_contenedor"] - 15

    # 2. Nombres y Apellidos
    estilo_nombres = estilos["nombres_apellidos"]
    c.setFont("Helvetica-Bold" if estilo_nombres["negrita"] else "Helvetica", estilo_nombres["tamano_fuente"])
    c.setFillColor(HexColor(estilo_nombres["color"]))
    c.drawString(10, y_base, nombres)

    # 3. Identificación Oficial
    y_base += estilo_nombres["interlineado"] - 2
    estilo_id = estilos["identificacion"]
    c.setFont("Helvetica-Bold" if estilo_id["negrita"] else "Helvetica", estilo_id["tamano_fuente"])
    c.setFillColor(HexColor(estilo_id["color"]))
    c.drawString(10, y_base - 14, identificacion)

    # 4. Código de Verificación Automático (mitad de tamaño)
    y_base_codigo = y_base - 28
    estilo_codigo = estilos["codigo_verificacion"]
    c.setFont("Helvetica", estilo_codigo["tamano_fuente"])
    c.setFillColor(HexColor(estilo_codigo["color"]))
    c.drawString(10, y_base_codigo, f"HASH: {codigo_verificacion}")

    c.save()
    output_stream.seek(0)