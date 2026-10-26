// Dockyyy chatbot API (FastAPI, /api/v2).
import { ENDPOINTS } from '../config/api';
import { request } from './httpClient';

const BASE = ENDPOINTS.chatbot;

export const chatbotService = {
  /** POST /ask — ask Dockyyy. `context` optionally feeds the live document. */
  ask: (query, context) =>
    request({ method: 'post', url: `${BASE}/ask`, data: { query, context } }),
};

export default chatbotService;
