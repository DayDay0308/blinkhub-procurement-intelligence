# ---- build stage: resolve dependencies with uv into a virtualenv ----
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

# ---- runtime stage: small image, non-root user ----
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/documents && chown app:app /data/documents
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
