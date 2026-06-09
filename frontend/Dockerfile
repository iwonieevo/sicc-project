# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

EXPOSE 3000

FROM base AS dev
CMD ["npm", "run", "dev"]

FROM base AS prod
RUN --mount=type=secret,id=frontend_env,target=/app/.env.production npm run build
CMD ["npm", "run", "start"]
