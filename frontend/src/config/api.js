// =====================================================================
// Central backend URL configuration.
//
// The SPA talks to the two backends directly — there is no reverse proxy:
//   Express  (auth, projects, files)  → VITE_EXPRESS_URL, default :3000
//   FastAPI  (chatbot, deep-scan,     → VITE_AI_URL,      default :8000
//             file editor, toolkit)
//
// Both send permissive CORS headers, so the browser may call them from
// http://localhost:5173. Set the two variables in the repo-root .env (Vite
// reads it via `envDir` in vite.config.js); in production point them at
// wherever the two services are deployed.
// =====================================================================

// Unset -> the local-dev default. "/" (or empty) -> '' = same origin, i.e.
// relative URLs like /api/auth: the container build for Kubernetes, where one
// Ingress serves the site and both APIs under a single address.
const fromEnv = (key, fallback) => {
  const v = import.meta.env?.[key];
  if (v === undefined || v === null) return fallback;
  return String(v).trim().replace(/\/+$/, '');
};

const EXPRESS = fromEnv('VITE_EXPRESS_URL', 'http://localhost:3000');
const AI = fromEnv('VITE_AI_URL', 'http://localhost:8000');

export const API = { EXPRESS, AI };

// Endpoint roots — what callers actually import.
export const ENDPOINTS = {
  auth:         `${EXPRESS}/api/auth`,
  projects:     `${EXPRESS}/api/projects`,

  // FastAPI routers (backend_ai/main.py mounts them at these prefixes):
  //   /api/v2/ask                       → Dockyyy chatbot
  //   /deepscan/api/v2/pipeline/stream  → deep-scan (document → LaTeX engine)
  //   /files/...                        → DocBot DOCX editor agent
  //   /toolkit/...                      → LaTeX toolkit
  chatbot:        `${AI}/api/v2`,
  deepScan:       `${AI}/deepscan`,
  deepScanCompile:`${AI}/deepscan/api/v2/compile`,
  fileEditor:     `${AI}/files`,
  toolkit:        `${AI}/toolkit`,
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
