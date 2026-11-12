FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CHIMERA_ENV=production PORT=8189
WORKDIR /app
COPY pyproject.toml LICENSE ./
COPY chimera/ chimera/
COPY web/ web/
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home chimera
USER chimera
EXPOSE 8189
CMD ["sh", "-c", "exec uvicorn chimera.api:app --host 0.0.0.0 --port ${PORT:-8189} --workers 1 --proxy-headers"]
