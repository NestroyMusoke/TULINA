FROM node:22-alpine AS builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    PORT=8080
WORKDIR /app
COPY --from=builder --chown=node:node /app/dist ./dist
COPY --chown=node:node frontend/server.mjs ./server.mjs
USER node
EXPOSE 8080
CMD ["node", "server.mjs"]
