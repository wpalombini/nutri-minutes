# The API image. Builds for linux/amd64 and linux/arm64.
FROM node:24.22.2-trixie-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

FROM node:24.22.2-trixie-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM node:24.22.2-trixie-slim
ENV NODE_ENV=production
WORKDIR /app
RUN groupadd --system --gid 10002 app \
    && useradd --system --uid 10002 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY package.json ./
USER app
EXPOSE 3000
CMD ["node", "--enable-source-maps", "dist/index.js"]
