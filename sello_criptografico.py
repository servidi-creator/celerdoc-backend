from io import BytesIO
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from firmador import generar_apariencia_firma

def firmar_documento(pdf_entrada, pdf_salida, clave_path, cert_path, nombres, cedula, codigo, trazo):
    appearance_stream = BytesIO()
    generar_apariencia_firma(
        trazo_base64=trazo,
        nombres=nombres,
        identificacion=cedula,
        codigo_verificacion=codigo,
        output_stream=appearance_stream
    )
    with open(pdf_entrada, 'rb') as inf:
        w = IncrementalPdfFileWriter(inf)
        fields.append_signature_field(w, sig_field_spec=fields.SigFieldSpec(sig_field_name='FirmaCelerdoc', on_page=0, box=(50, 50, 250, 150)))
        signer = signers.SimpleSigner.load(key_file=clave_path, cert_file=cert_path)
        meta = signers.PdfSignatureMetadata(field_name='FirmaCelerdoc', reason='Firma Celerdoc', location='Antioquia')
        with open(pdf_salida, 'wb') as outf:
            signers.sign_pdf(w, meta, signer=signer, output=outf)
    print('Módulo sello_criptografico.py actualizado correctamente.')
