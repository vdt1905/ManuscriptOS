// DocBot file-editor API (FastAPI, /files).
import { ENDPOINTS } from '../config/api';
import { request } from './httpClient';

const BASE = ENDPOINTS.fileEditor;

export const fileEditorService = {
  /** GET /documents — list editable documents. */
  listDocuments: () => request({ method: 'get', url: `${BASE}/documents` }),

  /** POST /chat — drive the DocBot editing agent. Body matches the server's
   *  ChatRequest: { message, document, user_id, session_id }. */
  chat: (message, { document, sessionId, userId = 'local_ui_user' } = {}) =>
    request({
      method: 'post',
      url: `${BASE}/chat`,
      data: { message, document, user_id: userId, session_id: sessionId },
    }),
};

export default fileEditorService;
