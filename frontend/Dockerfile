FROM node:22-slim AS base
WORKDIR /app
COPY package.json ./
RUN npm install

# Default target -- unchanged from before: source is bind-mounted over
# this in docker-compose.yml, `next dev` recompiles routes on demand.
# Fine for active development; NOT what a demo/production run should
# use -- see the `prod` target below (measured during the v1.0.1
# performance audit: a route's FIRST request in dev mode compiles on
# demand and can take 10-40+ seconds; every request after is fast,
# but that first hit is exactly what a live demo can't afford).
FROM base AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# Production target: builds ahead of time (`next build`), serves the
# already-compiled output (`next start`) -- no route ever pays a
# compile-on-first-request cost. Used by docker-compose.prod.yml,
# which also drops the dev compose file's source bind-mount so this
# built output is what actually serves, not live source.
FROM base AS builder
COPY . .
RUN npm run build

FROM node:22-slim AS prod
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["npm", "start"]
