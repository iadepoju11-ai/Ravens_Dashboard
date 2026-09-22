# Multi-stage: build the static production bundle, then serve it with
# nginx -- never the Vite dev server (docker-compose.yml's `web` service
# bind-mounts source and runs `npm run dev`, dev-only). This is the one
# used for staging/production, and is genuinely new: no Dockerfile
# existed for this app before (docker-compose.yml's `web` service, and
# docs/local-development.md's "docker compose up web", referenced one
# that was never actually built -- caught while building Phase 7A).
#
# VITE_* variables are read via import.meta.env at *build* time (Vite
# inlines them into the bundle as static strings) -- there is no
# runtime env-var injection for a static file server, so they must be
# passed as build args, not container environment variables. A
# different backend/OIDC host means a fresh image, not a config change.
FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ARG VITE_OIDC_AUTHORITY
ARG VITE_OIDC_CLIENT_ID
ARG VITE_OIDC_REDIRECT_URI
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_OIDC_AUTHORITY=${VITE_OIDC_AUTHORITY} \
    VITE_OIDC_CLIENT_ID=${VITE_OIDC_CLIENT_ID} \
    VITE_OIDC_REDIRECT_URI=${VITE_OIDC_REDIRECT_URI}

RUN npm run build

FROM nginx:1.27-alpine AS serve

# apk upgrade (CHECKLIST.md Phase 7D) -- a real `trivy` scan of this image
# found a CRITICAL, fixed OpenSSL CVE (libcrypto3/libssl3) in the base
# image's own OS packages that `nginx:1.27-alpine` hadn't been rebuilt
# with yet; upgrading at build time picks up whatever patched packages
# Alpine's repos already have.
RUN apk update && apk upgrade --no-cache

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
