// DeepScan API (FastAPI, /deepscan).
//
// Most calls are plain JSON through request(). TWO are special and use fetch
// directly (documented inline): the SSE pipeline stream and the compile call
// that returns a PDF *blob* or a JSON error. The A3 `useSSE` hook will own the
// streaming loop; streamRaw() here just exposes the endpoint + body builder.
import { ENDPOINTS, authHeaders } from '../config/api';
import { request } from './httpClient';

const BASE = ENDPOINTS.deepScan;

export const deepScanService = {
  /** The SSE pipeline endpoint + a FormData builder. The actual streaming loop
   *  lives in the A3 useSSE hook (with AbortController cleanup). */
  pipelineUrl: `${BASE}/api/v2/pipeline/stream`,
  buildPipelineForm: (file, { style, model }) => {
    const fd = new FormData();
    fd.append('file', file, file.name);
    if (style) fd.append('style', style);
    if (model) fd.append('model', model);
    return fd;
  },

  /** Build { url, init } for useSSE().start() — POST multipart + Bearer auth. */
  pipelineStreamArgs: (file, { style, model }) => ({
    url: `${BASE}/api/v2/pipeline/stream`,
    init: {
      method: 'POST',
      headers: authHeaders(),
      body: deepScanService.buildPipelineForm(file, { style, model }),
    },
  }),

  /**
   * Compile LaTeX → PDF. Returns { ok, blob } on success or { ok:false, error,
   * notes } on failure. Uses fetch because the response is either a PDF blob or
   * a JSON error body — request()'s single-shape contract doesn't fit.
   */
  compile: async (latex, job = null) => {
    const res = await fetch(ENDPOINTS.deepScanCompile, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ latex, job }),
    });
    const ctype = res.headers.get('content-type') || '';
    if (res.ok && ctype.includes('application/pdf')) {
      let notes = [];
      try { notes = JSON.parse(res.headers.get('X-Latex-Notes') || '[]'); } catch { /* ignore */ }
      return { ok: true, blob: await res.blob(), notes };
    }
    const data = await res.json().catch(() => ({}));
    return {
      ok: false,
      status: res.status,
      error: data.log || data.message || 'Compilation failed.',
      notes: Array.isArray(data.notes) ? data.notes : [],
      tectonicAvailable: data.tectonic_available,
    };
  },

  /** POST /api/v2/latex-to-docx — DOCX built from the final LaTeX (styled like
   *  the PDF) and handed to the AI document agent. Returns { filename }. */
  latexToDocx: async (latex, { job = null, style = 'ieee', name = null } = {}) => {
    const res = await fetch(`${BASE}/api/v2/latex-to-docx`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ latex, job, style, name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.filename) {
      throw { message: data.detail || data.error || `Conversion failed (${res.status})`, status: res.status };
    }
    return data;
  },

  /** POST /api/v2/assets/:job/:n — upload an image for a missing figure (Phase I). */
  uploadFigure: async (job, n, file, latex = '') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('latex', latex);
    const res = await fetch(`${BASE}/api/v2/assets/${job}/${n}`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw { message: data.detail || `Upload failed (${res.status})`, status: res.status };
    }
    return data; // { ok, n, filename, rel_path, latex }
  },

  /** Absolute URL for an extracted asset image. */
  assetUrl: (job, filename) => `${BASE}/api/v2/assets/${job}/${filename}`,
  /** Absolute URL to download a formatted file. */
  downloadUrl: (filename) => `${BASE}/api/v2/download/${filename}`,
};

export default deepScanService;
