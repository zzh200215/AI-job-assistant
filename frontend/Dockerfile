# ============================================================
# Frontend Dockerfile — Vue 3 build → nginx serving
# ============================================================
# ---- Build stage ----
FROM node:18-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# VITE_API_BASE is baked into the JS bundle at build time.
# Default /api means all API calls go to the same origin,
# where nginx proxies them to the backend container.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---- Production stage ----
FROM nginx:1.25-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
