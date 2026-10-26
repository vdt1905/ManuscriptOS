# ─────────────────────────────────────────────────────────────
# auth-service — Node/Express: sign-up/login (JWT) and projects
# Build context: ./backend
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

# Dependencies first (cached until package.json / the lockfile change).
# npm ci installs exactly what package-lock.json pins: reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --chown=node:node . .

# The official image ships an unprivileged "node" user (uid 1000). A numeric
# USER lets Kubernetes verify runAsNonRoot.
USER 1000:1000
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:3000/healthz"]

CMD ["node", "server.js"]
