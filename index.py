import os
import json
import base64
import fitz  # PyMuPDF
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Celerdoc API - Motor de Firma Electrónica",
    description="Backend de procesamiento y sellado seguro de documentos PDF",
    version="2.0.0"
)

# Habilitar CORS para permitir peticiones desde Wix y cualquier origen seguro
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ruta del archivo de configuración del espejo
RUTA_CONFIG_ESPEJO = os.path.join("configuraciones", "json_firmas", "configuracion_espejo.json")


@app.get("/")
def ruta_raiz():
    return {
        "sistema": "Celerdoc API",
        "estado": "Operativo",
        "fecha_servidor": datetime.utcnow().isoformat()
    }


@app.post("/obtener-espejo")
async def obtener_espejo(
    archivo: UploadFile = File(...),
    numero_pagina: int = Form(default=-1)
):
    """
    Extrae quirúrgicamente una página específica (o la última por defecto)
    del PDF original y la convierte a una imagen en Base64 para el visor espejo.
    """
    try:
        # Cargar configuración si existe, o usar valores seguros por defecto
        resolucion_dpi = 150
        formato_img = "png"
        if os.path.exists(RUTA_CONFIG_ESPEJO):
            with open(RUTA_CONFIG_ESPEJO, "r", encoding="utf-8") as f:
                config = json.load(f)
                resolucion_dpi = config.get("resolucion_dpi", 150)
                formato_img = config.get("formato_salida", "png")

        # Leer el documento PDF en memoria
        contenido_bytes = await archivo.read()
        if not contenido_bytes:
            raise HTTPException(status_code=400, detail="El archivo enviado está vacío.")

        doc = fitz.open(stream=contenido_bytes, filetype="pdf")
        total_paginas = len(doc)

        if total_paginas == 0:
            raise HTTPException(status_code=400, detail="El PDF no contiene páginas válidas.")

        # Si el número de página es -1 o superior al total, selecciona la última hoja
        if numero_pagina == -1 or numero_pagina > total_paginas:
            indice_pagina = total_paginas - 1
        else:
            indice_pagina = max(0, numero_pagina - 1)

        pagina = doc.load_page(indice_pagina)

        # Renderizar la página como imagen
        pix = pagina.get_pixmap(dpi=resolucion_dpi)
        imagen_bytes = pix.tobytes(formato_img)
        imagen_base64 = base64.b64encode(imagen_bytes).decode("utf-8")

        # Dimensiones originales en puntos de PDF
        rect = pagina.rect

        doc.close()

        return {
            "status": "success",
            "total_paginas": total_paginas,
            "pagina_actual": indice_pagina + 1,
            "dimensiones": {
                "ancho": rect.width,
                "alto": rect.height
            },
            "espejo_base64": f"data:image/{formato_img};base64,{imagen_base64}"
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "mensaje": f"Error al generar espejo: {str(e)}"}
        )


if __name__ == "__main__":
    import uvicorn
    puerto = int(os.environ.get("PORT", 8000))
    uvicorn.run("index:app", host="0.0.0.0", port=puerto, reload=True)