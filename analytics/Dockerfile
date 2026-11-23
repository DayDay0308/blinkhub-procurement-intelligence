FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    DAGSTER_HOME=/opt/dagster/home PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
# Parse the dbt project at build time so Dagster starts with a ready manifest (no DB needed).
RUN mkdir -p $DAGSTER_HOME && cd dbt && dbt parse --profiles-dir . --quiet
EXPOSE 3000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
