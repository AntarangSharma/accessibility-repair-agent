FROM node:22.22.2-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:0.11.9 AS uv
FROM python:3.12.13-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=uv /uv /uvx /usr/local/bin/
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts && npx --no-install playwright install --with-deps chromium
COPY . .
RUN uv sync --frozen --python 3.12 \
    && useradd --create-home app \
    && mkdir -p /app/.state /app/reports \
    && chown -R app:app /app /tmp/uv-cache
USER app
CMD ["uv", "run", "--frozen", "python", "-m", "repair_agent.cli", "serve"]
