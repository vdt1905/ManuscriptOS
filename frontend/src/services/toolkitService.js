// LaTeX Toolkit API (FastAPI, /toolkit).
import { ENDPOINTS, authHeaders } from '../config/api';
import { request } from './httpClient';

const BASE = ENDPOINTS.toolkit;

export const toolkitService = {
  /** POST /table — CSV/grid → LaTeX tabular. */
  table: (body) => request({ method: 'post', url: `${BASE}/table`, data: body }),

  /** POST /equation — text → LaTeX math. */
  equation: (description, display = true) =>
    request({ method: 'post', url: `${BASE}/equation`, data: { description, display } }),

  /** POST /bibtex — references → .bib. */
  bibtex: (references, enrich = false) =>
    request({ method: 'post', url: `${BASE}/bibtex`, data: { references, enrich } }),

  /** GET /templates — starter template list. */
  listTemplates: () => request({ method: 'get', url: `${BASE}/templates` }),

  /** GET /templates/:id — one template's .tex. */
  getTemplate: (id) => request({ method: 'get', url: `${BASE}/templates/${id}` }),

  /** POST /chat — LaTeX assistant. */
  chat: (message) => request({ method: 'post', url: `${BASE}/chat`, data: { message } }),

  /** POST /convert — upload DOCX/PDF/TXT → LaTeX (multipart). */
  convert: (file, style = 'article') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('style', style);
    return request({
      method: 'post',
      url: `${BASE}/convert`,
      data: fd,
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  /**
   * POST /export?to=pdf|docx|md — LaTeX → file. Returns { ok, blob, ext } or a
   * normalized failure. fetch (not request) because the body is a binary blob.
   */
  export: async (latex, to = 'pdf') => {
    const res = await fetch(`${BASE}/export?to=${to}`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ latex }),
    });
    const ctype = res.headers.get('content-type') || '';
    if (res.ok && !ctype.includes('application/json')) {
      return { ok: true, blob: await res.blob(), ext: to === 'md' ? 'md' : to };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: false, error: data.log || `Export failed (${res.status})` };
  },
};

export default toolkitService;
