# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci

COPY . .

EXPOSE 3000

FROM base AS dev
CMD ["npm", "run", "dev"]

FROM base AS build
RUN --mount=type=secret,id=frontend_env,target=/app/.env.production npm run build

FROM nginx:1.29-alpine AS prod
ENV PORT=3000
ENV BACKEND_URL=http://backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/build/client /usr/share/nginx/html
EXPOSE 3000
