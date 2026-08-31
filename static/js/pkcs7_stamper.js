/**
 * Módulo independiente: Celerdoc PKCS#7 Stamper
 * Gestiona:
 * 1. Secuencia estricta: 🔒 Candado -> Código QR -> Texto Hash continuo (sin solapamientos).
 * 2. Las 3 condiciones de ubicación (Vertical izquierda -> Pie de página horizontal -> Solo hoja de auditoría).
 */

export const PKCS7Stamper = {
  config: {
    hash: "c2a9d8f3e5b10478bc64df91e021a876fa5e9b31d472c08416d8a9e6b21c45df",
    algoritmo: "SHA256withRSA / PKCS#7 Container",
    qr_data: "https://celerdoc.com/verify?sig=c2a9d8f3e5b10478bc64df91e021a876",
    status: "VALID"
  },

  async cargarConfiguracion() {
    try {
      const resp = await fetch("/configuraciones/json_firmas/codigo_pkcs7.json");
      if (resp.ok) {
        const data = await resp.json();
        if (data.pkcs7_metadata) {
          this.config = { ...this.config, ...data.pkcs7_metadata };
        }
      }
    } catch (e) {
      console.warn("Utilizando metadatos PKCS#7 por defecto.", e);
    }
    return this.config;
  },

  renderizarEstampa(contenedorPagina, markerFirmaElement, onPosicionDeterminada) {
    const badgeExistente = document.getElementById('pkcs7BadgeElement');
    if (badgeExistente) badgeExistente.remove();

    const badge = document.createElement('div');
    badge.id = 'pkcs7BadgeElement';
    badge.className = 'pkcs7-badge-container';
    
    // Secuencia lineal estricta: 1. Candado | 2. QR | 3. Texto Hash completo alineado a la izquierda sin tocar la imagen
    badge.innerHTML = `
      <div class="pkcs7-lock-icon">🔒</div>
      <div class="pkcs7-qr-slot" id="pkcs7QrSlot"></div>
      <div class="pkcs7-data-text">
        <strong style="color: #3366CC;">PKCS#7 VALIDATION:</strong>
        <span class="pkcs7-hash-val">${this.config.hash}</span>
        <span class="pkcs7-status-tag" style="color: #16a34a; font-weight: bold;">[${this.config.status}]</span>
      </div>
    `;

    // CONDICIÓN 1: Vertical extremo izquierdo inferior hacia arriba
    badge.className = 'pkcs7-badge-container pkcs7-pos-left-bottom-up';
    contenedorPagina.appendChild(badge);
    this._generarQR('pkcs7QrSlot', this.config.qr_data);

    const markerRect = markerFirmaElement.getBoundingClientRect();
    let badgeRect = badge.getBoundingClientRect();

    const colisionVertical = !(
      badgeRect.top > markerRect.bottom ||
      badgeRect.right < markerRect.left ||
      badgeRect.bottom < markerRect.top ||
      badgeRect.left > markerRect.right
    );

    if (!colisionVertical) {
      if (onPosicionDeterminada) onPosicionDeterminada('left_vertical', this.config);
      return;
    }

    // CONDICIÓN 2: Horizontal en zona de pie de página
    badge.className = 'pkcs7-badge-container pkcs7-pos-bottom-footer';
    badgeRect = badge.getBoundingClientRect();

    const colisionFooter = !(
      badgeRect.top > markerRect.bottom ||
      badgeRect.right < markerRect.left ||
      badgeRect.bottom < markerRect.top ||
      badgeRect.left > markerRect.right
    );

    if (!colisionFooter) {
      if (onPosicionDeterminada) onPosicionDeterminada('bottom_above_footer', this.config);
      return;
    }

    // CONDICIÓN 3: Reubicación exclusiva a tabla de auditoría
    badge.remove();
    if (onPosicionDeterminada) onPosicionDeterminada('audit_table_only', this.config);
  },

  _generarQR(elementId, qrData) {
    const slot = document.getElementById(elementId);
    if (slot && typeof QRCode !== "undefined") {
      slot.innerHTML = '';
      new QRCode(slot, {
        text: qrData,
        width: 28,
        height: 28,
        colorDark: "#0f172a",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M
      });
    }
  }
};