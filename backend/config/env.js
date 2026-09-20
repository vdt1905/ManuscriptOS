// Loads environment variables before any other module reads process.env.
// ES module imports are hoisted, so this must stay the FIRST import in server.js
// (cloudinary.js, for one, reads its keys at import time).
//
// backend/.env wins if present; the repo-root .env (shared with backend_ai and
// docker compose) fills in everything else. Neither overrides variables that are
// already set, so docker compose's environment still takes precedence.
import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({ path: path.join(here, '..', '.env'), quiet: true });
dotenv.config({ path: path.join(here, '..', '..', '.env'), quiet: true });
