FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY backend ./backend
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    TULINA_DATABASE_PATH=/var/lib/tulina/tulina.sqlite3
RUN groupadd --system tulina \
    && useradd --system --gid tulina --home-dir /app tulina \
    && mkdir -p /app /var/lib/tulina \
    && chown -R tulina:tulina /app /var/lib/tulina
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=tulina:tulina data/fixtures ./data/fixtures
COPY --chown=tulina:tulina contracts ./contracts
USER tulina
EXPOSE 8080
CMD ["uvicorn", "backend.tulina.api:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
