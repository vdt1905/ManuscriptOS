// =====================================================================
// Central backend URL configuration (Phase E.2 — NGINX single origin).
//
// Every request goes to ONE origin: the NGINX reverse proxy. NGINX routes
// /api/auth + /api/projects → Express, and /api/ai/* → FastAPI, internally.
// The SPA never knows (or needs to know) there are two backends.
//
// Set VITE_API_URL to wherever NGINX is reachable:
//   • local dev:  http://localhost:80   (the compose nginx service)
//   • production: https://api.yourdomain.com
// =====================================================================

const fromEnv = (key, fallback) => {
  const v = import.meta.env?.[key];
  return v && v.trim() ? v.trim().replace(/\/+$/, '') : fallback;
};

// The single public origin — the NGINX proxy.
//   Dev (no .env.local needed): empty string → relative URLs (/api/auth etc.).
//     Vite proxy intercepts /api/* → http://localhost:80 so the browser never
//     makes a cross-origin request → zero CORS issues during development.
//   Prod: set VITE_API_URL=https://api.yourdomain.com in your build environment.
//   Legacy: VITE_EXPRESS_URL still accepted so older .env files keep working.
const BASE = fromEnv('VITE_API_URL', fromEnv('VITE_EXPRESS_URL', ''));

export const API = { BASE };

// AI routes live under /api/ai/* (NGINX strips that prefix before FastAPI).
const AI_ROOT = `${BASE}/api/ai`;

// Endpoint roots — what callers actually import. All hang off the one origin.
export const ENDPOINTS = {
  auth:         `${BASE}/api/auth`,
  projects:     `${BASE}/api/projects`,

  // AI service mounts (NGINX → FastAPI):
  //   /api/v2/ask                       → Dockyyy chatbot
  //   /deepscan/api/v2/pipeline/stream  → deep-scan (core document→LaTeX engine)
  //   /files/...                        → DocBot DOCX editor agent
  //   /toolkit/...                      → LaTeX Toolkit (Phase H)
  chatbot:        `${AI_ROOT}/api/v2`,
  deepScan:       `${AI_ROOT}/deepscan`,
  deepScanCompile:`${AI_ROOT}/deepscan/api/v2/compile`,
  fileEditor:     `${AI_ROOT}/files`,
  toolkit:        `${AI_ROOT}/toolkit`,
};

// =====================================================================
// Auth helpers (Phase 3). Express signs a JWT on login and the SPA stores
// the raw token under 'token' in localStorage (see useAuthStore.js). The
// Python services share the same secret and verify the same header.
// =====================================================================

export function getAuthToken() {
  try {
    return localStorage.getItem('token') || null;
  } catch {
    return null;
  }
}

/** Returns headers including Bearer auth when a token is available. Use
 *  for fetch() calls — axios uses the global interceptor below. */
export function authHeaders(extra = {}) {
  const t = getAuthToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
}

// --------------------------------------------------------------------------
// Global axios interceptor — attaches Bearer auth to every axios request
// across the SPA so we don't need per-call-site edits. Runs once on first
// import of this module (which every API caller already does).
// --------------------------------------------------------------------------
import axios from 'axios';

let _axiosInterceptorInstalled = false;

function _installAxiosInterceptor() {
  if (_axiosInterceptorInstalled) return;
  _axiosInterceptorInstalled = true;
  axios.interceptors.request.use((cfg) => {
    if (!cfg.headers?.Authorization && !cfg.headers?.authorization) {
      const t = getAuthToken();
      if (t) {
        cfg.headers = cfg.headers || {};
        cfg.headers.Authorization = `Bearer ${t}`;
      }
    }
    return cfg;
  });
  installSessionExpiryHandler(axios);
}

/**
 * A 401 on any authenticated call means the stored token is no longer valid
 * (expired, or the server's secret changed). Drop it and send the user to the
 * login page instead of leaving them "logged in" with every request failing.
 * Login/signup 401s are the user's own bad credentials and are left alone.
 */
export function installSessionExpiryHandler(instance) {
  instance.interceptors.response.use(
    (res) => res,
    (error) => {
      const url = error?.config?.url || '';
      const isAuthCall = url.includes('/api/auth/login') || url.includes('/api/auth/signup');
      if (error?.response?.status === 401 && !isAuthCall && getAuthToken()) {
        try { localStorage.removeItem('token'); } catch { /* ignore */ }
        if (window.location.pathname !== '/') window.location.assign('/');
      }
      return Promise.reject(error);
    },
  );
}
_installAxiosInterceptor();

export default ENDPOINTS;
