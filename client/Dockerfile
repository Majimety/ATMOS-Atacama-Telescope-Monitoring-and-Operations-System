###############################################################################
# client/Dockerfile  —  ATMOS React frontend (Vite → Nginx)
###############################################################################
FROM node:22-alpine AS builder

WORKDIR /build
ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000

COPY package.json package-lock.json ./
RUN npm ci --silent

COPY . .
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS final

COPY --from=builder /build/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://localhost/health || exit 1

###############################################################################
# docker/nginx.conf
###############################################################################
# Save as: client/docker/nginx.conf
# ─────────────────────────────────────────────────────────────────────────────
# server {
#     listen 80;
#     server_name _;
#     root /usr/share/nginx/html;
#     index index.html;
#
#     # Security headers
#     add_header X-Frame-Options DENY;
#     add_header X-Content-Type-Options nosniff;
#     add_header Referrer-Policy strict-origin-when-cross-origin;
#     add_header Permissions-Policy "camera=(), microphone=(), geolocation=()";
#
#     # Gzip
#     gzip on;
#     gzip_types text/plain text/css application/javascript application/json;
#     gzip_min_length 1024;
#
#     # Cache static assets aggressively (Vite fingerprints them)
#     location ~* \.(js|css|woff2|png|svg|ico)$ {
#         expires 1y;
#         add_header Cache-Control "public, immutable";
#     }
#
#     # Health probe
#     location /health {
#         return 200 "ok";
#         add_header Content-Type text/plain;
#     }
#
#     # SPA fallback — all routes → index.html
#     location / {
#         try_files $uri $uri/ /index.html;
#     }
# }