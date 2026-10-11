# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/janos/.venv/bin:$PATH" \
    JANOS_DATA_DIR=/var/lib/janos \
    JANOS_PRODUCTION=true \
    TF_CPP_MIN_LOG_LEVEL=2
WORKDIR /opt/janos
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra inference --no-dev --no-cache
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY wsgi.py gunicorn.conf.py ./
RUN python -c "from pathlib import Path; p=Path('app/janos-vgg16-model.h5'); assert p.open('rb').read(8) == b'\x89HDF\r\n\x1a\n', 'Run git lfs pull before building'" \
    && groupadd --gid 10001 janos \
    && useradd --uid 10001 --gid janos --no-create-home janos \
    && mkdir -p /var/lib/janos/uploads \
    && chown -R janos:janos /var/lib/janos
USER janos
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD ["python", "scripts/healthcheck.py"]
ENTRYPOINT ["python", "scripts/entrypoint.py"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
