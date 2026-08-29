import os
import tempfile
from PyPDF2 import PdfReader, PdfWriter, PageObject
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from firmador import generar_apariencia_firma

def firmar_documento(
    pdf_entrada: str,
    pdf_salida: str,
    clave_path: str,
    cert_path: str,
    nombres: str,
    cedula: str,
    codigo: str,
    trazo: str,
    pagina: int = 1,
    coordenadas: tuple = (50.0, 80.0),
    motivo: str = "Firma Celerdoc",
    ubicacion: str = "Antioquia, Colombia"
) -> str:
    
    # 1. Leer el PDF original para detectar cantidad de páginas y dimensiones
    reader = PdfReader(pdf_entrada)
    total_paginas = len(reader.pages)
    
    temp_pdf_path = pdf_entrada # Por defecto operamos sobre el original
    
    # 2. Lógica de Desborde: Si la página solicitada es mayor al total, creamos una hoja en blanco
    if pagina > total_paginas:
        writer = PdfWriter()
        # Copiar todas las páginas existentes
        for p in reader.pages:
            writer.add_page(p)
            
        # Tomar las medidas de la última página para que la nueva sea idéntica
        ultima_pagina = reader.pages[-1]
        ancho_pdf = float(ultima_pagina.mediabox.width)
        alto_pdf = float(ultima_pagina.mediabox.height)
        
        # Crear y añadir la página en blanco
        nueva_pagina = PageObject.create_blank_page(width=ancho_pdf, height=alto_pdf)
        writer.add_page(nueva_pagina)
        
        # Guardar temporalmente este nuevo PDF con la hoja extra
        fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(temp_pdf_path, "wb") as f_temp:
            writer.write(f_temp)
            
        # La firma irá en la última página recién creada (índice base 0)
        pagina_objetivo = total_paginas
    else:
        # No hay desborde, firmamos en la página normal solicitada
        pagina_objetivo = pagina - 1 # PyHanko usa índice desde 0
        pagina_obj = reader.pages[pagina_objetivo]
        ancho_pdf = float(pagina_obj.mediabox.width)
        alto_pdf = float(pagina_obj.mediabox.height)

    # 3. Conversión de Porcentajes del Frontend a Puntos exactos del PDF
    x_pct, y_pct = coordenadas
    
    # Centro X en puntos
    centro_x = (x_pct / 100.0) * ancho_pdf
    
    # Centro Y en el frontend (donde Y=0 es arriba), en PDF (Y=0 es abajo)
    centro_y_front = (y_pct / 100.0) * alto_pdf
    centro_y_pdf = alto_pdf - centro_y_front
    
    # Dimensiones fijas de la caja de firma en el PDF (Ancho: 160pt, Alto: 60pt)
    ancho_firma = 160
    alto_firma = 60
    
    # Coordenadas PyHanko: (x1, y1, x2, y2) -> (izq_inferior_x, izq_inferior_y, der_superior_x, der_superior_y)
    x1 = int(centro_x - (ancho_firma / 2))
    y1 = int(centro_y_pdf - (alto_firma / 2))
    x2 = int(centro_x + (ancho_firma / 2))
    y2 = int(centro_y_pdf + (alto_firma / 2))
    
    box_firma = (x1, y1, x2, y2)

    # 4. Proceso Criptográfico con PyHanko
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_app:
        tmp_apariencia_path = tmp_app.name

    try:
        # Generar estampa visual con tus parámetros predefinidos
        with open(tmp_apariencia_path, "wb") as f_app:
            generar_apariencia_firma(
                trazo_base64=trazo,
                nombres=nombres,
                identificacion=cedula,
                codigo_verificacion=codigo,
                output_stream=f_app
            )

        # Quitar el borde automático para que quede limpio
        stamp_style = stamp.StaticStampStyle.from_pdf_file(tmp_apariencia_path, border_width=0)

        with open(temp_pdf_path, "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            fields.append_signature_field(
                w,
                sig_field_spec=fields.SigFieldSpec(
                    sig_field_name="FirmaCelerdoc",
                    on_page=pagina_objetivo,
                    box=box_firma
                )
            )
            # Cargar certificados PKCS#7
            signer = signers.SimpleSigner.load(key_file=clave_path, cert_file=cert_path)
            meta = signers.PdfSignatureMetadata(
                field_name="FirmaCelerdoc",
                reason=motivo,
                location=ubicacion
            )
            pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=stamp_style)

            # Sellar y guardar
            with open(pdf_salida, "wb") as outf:
                pdf_signer.sign_pdf(w, output=outf)

        return pdf_salida

    finally:
        # Limpieza de archivos temporales de seguridad
        if os.path.exists(tmp_apariencia_path):
            try:
                os.remove(tmp_apariencia_path)
            except Exception:
                pass
        
        if temp_pdf_path != pdf_entrada and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except Exception:
                pass