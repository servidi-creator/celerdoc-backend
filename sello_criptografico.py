import hashlib
from datetime import datetime

def generar_huella_sha256(datos_documento):
    """
    Toma los datos del documento y la firma, y genera una huella 
    criptográfica única (SHA-256) que garantiza que no fue alterado.
    """
    # Convertimos el texto a un formato que la máquina puede cifrar
    datos_en_bytes = datos_documento.encode('utf-8')
    
    # Aplicamos el candado SHA-256
    huella_segura = hashlib.sha256(datos_en_bytes).hexdigest()
    
    return huella_segura

def sellar_pdf_celerdoc(ruta_entrada, ruta_salida, datos_firmante):
    """
    Esta es la función principal que usaremos más adelante con PyHanko
    para inyectar el sello visual y el candado dentro del archivo PDF.
    """
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    huella_generada = generar_huella_sha256(datos_firmante)
    
    print("\n--- NUEVO SELLO CELERDOC GENERADO ---")
    print(f"Fecha de firma: {fecha_hoy}")
    print(f"Huella Criptográfica (SHA-256): {huella_generada}")
    print("---------------------------------------\n")
    
    return huella_generada