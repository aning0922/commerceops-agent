FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS runtime
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.25
COPY pyproject.toml uv.lock .python-version ./
COPY backend ./backend
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" LANGSMITH_TRACING=false
CMD ["python", "-m", "commerceops.entrypoints.database", "revision"]

FROM runtime AS test
RUN uv sync --frozen --no-editable
COPY tests ./tests
COPY scripts ./scripts
