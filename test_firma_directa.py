import os
import tempfile
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from firmador import generar_apariencia_firma

pdf_entrada = "documento_prueba.pdf"
pdf_salida = "documento_firmado_v2.pdf"
clave_path = "key.pem"
cert_path = "cert.pem"
nombres = "JORGE IVAN BARRERA SANCHEZ"
cedula = "C.C. 123456789"
codigo = "CELERDOC-HASH-2026"
trazo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
    tmp_apariencia_path = tmp.name

try:
    with open(tmp_apariencia_path, "wb") as f_app:
        generar_apariencia_firma(
            trazo_base64=trazo,
            nombres=nombres,
            identificacion=cedula,
            codigo_verificacion=codigo,
            output_stream=f_app
        )

    stamp_style = stamp.StaticStampStyle.from_pdf_file(tmp_apariencia_path, border_width=0)

    with open(pdf_entrada, "rb") as inf:
        w = IncrementalPdfFileWriter(inf)
        fields.append_signature_field(
            w,
            sig_field_spec=fields.SigFieldSpec(
                sig_field_name="FirmaCelerdoc",
                on_page=0,
                box=(50, 50, 270, 150)
            )
        )
        signer = signers.SimpleSigner.load(key_file=clave_path, cert_file=cert_path)
        meta = signers.PdfSignatureMetadata(
            field_name="FirmaCelerdoc",
            reason="Firma Celerdoc",
            location="Antioquia"
        )
        pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=stamp_style)

        with open(pdf_salida, "wb") as outf:
            pdf_signer.sign_pdf(w, output=outf)

    print("EXITO: Generado documento_firmado_v2.pdf")
finally:
    if os.path.exists(tmp_apariencia_path):
        try:
            os.remove(tmp_apariencia_path)
        except Exception:
            pass
