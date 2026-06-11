# syntax=docker/dockerfile:1
# LQ.AI web shell — standalone SvelteKit SPA (ADR-F006, F0-S6).
# Stage 1 builds the static bundle; stage 2 serves it with nginx on :8080,
# keeping the pre-S6 container contract (port 8080 + GET /health) so
# compose / helm / the caddy overlay keep working unchanged.

FROM node:22-alpine AS build
# Vite/SvelteKit bakes PUBLIC_* env vars into the static bundle at build
# time. Production: leave unset (relative /api/v1 behind a reverse proxy).
# Local Compose dev: passed via docker-compose.yml `args:` from .env's
# PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1 — it must be the
# URL as the BROWSER sees it.
ARG PUBLIC_LQ_AI_API_BASE_URL=/api/v1

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Writing the build arg into .env is the reliable substitution path for
# Vite's static replacement of $env/dynamic/public reads in client code.
RUN printf 'PUBLIC_LQ_AI_API_BASE_URL=%s\n' "${PUBLIC_LQ_AI_API_BASE_URL}" > .env \
    && npm run build

# 1.28 is the maintained stable line (1.27 mainline stopped receiving
# nginx/alpine patches when 1.28 shipped) — keep this on a supported tag.
FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK CMD wget -q -O /dev/null http://localhost:8080/health || exit 1
