# ─────────────────────────────────────────────────────────────
# frontend — React single-page app
# Build context: ./frontend
# Multi-stage: Node builds the static files, a tiny web server serves them.
# The final image contains no Node, no source code, no node_modules.
# ─────────────────────────────────────────────────────────────

# Stage 1: build
FROM node:22-alpine AS build
WORKDIR /app/frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Where the browser reaches the two APIs, baked in at build time.
# "/" (the default) = same origin: in Kubernetes the Ingress serves the site
# and both APIs under one address, so the app uses relative URLs like
# /api/auth. docker compose passes http://localhost:... instead.
ARG VITE_EXPRESS_URL=/
ARG VITE_AI_URL=/
RUN VITE_EXPRESS_URL="$VITE_EXPRESS_URL" VITE_AI_URL="$VITE_AI_URL" npm run build

# Stage 2: serve (unprivileged nginx: runs as a non-root user on port 8080)
FROM nginxinc/nginx-unprivileged:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
# The base image's unprivileged "nginx" user (uid 101), stated explicitly.
USER 101
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
