FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json ./
COPY frontend/build.mjs ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    FLASK_DEBUG=False

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
COPY --from=frontend-build --chown=app:app /frontend/dist ./frontend/dist

RUN mkdir -p /app/data && chown -R app:app /app

USER app

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os; from urllib.request import urlopen; urlopen('http://127.0.0.1:' + os.environ.get('PORT', '10000') + '/api/v1/health', timeout=5)"

CMD ["sh", "-c", "python -m src.cli bootstrap-admin && exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --worker-class gthread --threads 2 --timeout 120 wsgi:app"]
