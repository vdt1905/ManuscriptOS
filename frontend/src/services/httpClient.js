// Shared HTTP client (Track A2 service layer).
//
// One axios instance + one request() wrapper that every service module goes
// through. Centralizes:
//   • auth        — inherits the global Bearer interceptor from config/api.js
//   • validation  — optionally Zod-parses the response (fail-open via parseTolerant)
//   • errors      — normalizes any failure to a consistent { message, status }
//
// Services never touch axios directly; components/stores never touch axios at
// all. This is the single place to add retry/timeout/refresh later.
import axios from 'axios';
import { installSessionExpiryHandler } from '../config/api'; // also installs the global auth interceptor
import { parseTolerant } from '../schemas';

// A dedicated instance so per-app defaults (timeout) don't leak into the global
// axios used by the interceptor module. The interceptor is registered on the
// global axios AND applies here because axios.create inherits global interceptors
// at request time only for the default instance — so we re-attach auth below to
// be safe and explicit.
export const http = axios.create({
  timeout: 120000, // 2 min — DeepScan compile/convert can be slow
});

// Attach Bearer auth to this instance too (explicit, independent of the global).
http.interceptors.request.use((cfg) => {
  if (!cfg.headers?.Authorization && !cfg.headers?.authorization) {
    let token = null;
    try { token = localStorage.getItem('token'); } catch { /* ignore */ }
    if (token) {
      cfg.headers = cfg.headers || {};
      cfg.headers.Authorization = `Bearer ${token}`;
    }
  }
  return cfg;
});
installSessionExpiryHandler(http);

/**
 * Normalize any thrown value (axios error, network error, plain error) into a
 * predictable shape services can rethrow and callers can rely on.
 * @param {unknown} error
 * @returns {{ message: string, status: number|null, data: any }}
 */
export function normalizeError(error) {
  // Axios error with a server response.
  if (error?.response) {
    const { status, data } = error.response;
    const message =
      data?.error || data?.message || data?.detail ||
      `Request failed (${status})`;
    return { message, status, data };
  }
  // Request made but no response (network down, CORS, timeout).
  if (error?.request) {
    return {
      message: error.code === 'ECONNABORTED'
        ? 'The request timed out. Please try again.'
        : 'Could not reach the server. Check your connection.',
      status: null,
      data: null,
    };
  }
  // Something else (programming error, etc.).
  return { message: error?.message || 'Unexpected error', status: null, data: null };
}

/**
 * Perform a request and return the (optionally Zod-validated) response data.
 * Throws a normalized error on failure.
 *
 * @template T
 * @param {import('axios').AxiosRequestConfig} config  axios config (method, url, data, …)
 * @param {object} [opts]
 * @param {import('zod').ZodType<T>} [opts.schema]  validate+shape the response data
 * @param {string} [opts.label]                     label for schema-drift warnings
 * @returns {Promise<T>}
 */
export async function request(config, { schema, label } = {}) {
  try {
    const res = await http.request(config);
    return schema ? parseTolerant(schema, res.data, label || config.url) : res.data;
  } catch (error) {
    throw normalizeError(error);
  }
}

export default { http, request, normalizeError };
