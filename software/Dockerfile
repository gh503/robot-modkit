# modkit 本地 REST API / 管网 / 世界仿真
# build: docker build -f software/Dockerfile -t modkit-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY software/pyproject.toml ./software/pyproject.toml
COPY software/modkit ./software/modkit
COPY software/networks ./software/networks
RUN pip install --no-cache-dir -e "software[api,world]" \
 && useradd --create-home --uid 10001 app \
 && chown -R app:app /app
USER app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/v1/health', timeout=3)"

# 远程绑定必须设置 MODKIT_API_KEY；compose 强制该变量。
CMD ["modkit", "serve", "--host", "0.0.0.0", "--port", "8080", "--allow-remote"]
