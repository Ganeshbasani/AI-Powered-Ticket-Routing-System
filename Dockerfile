# ---------- Frontend build ----------
FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json ./package.json
COPY frontend/build.mjs ./build.mjs
COPY frontend/src ./src

RUN npm run build


# ---------- Python production runtime ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    FLASK_DEBUG=False \
    PORT=10000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

COPY --from=frontend-build --chown=app:app /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/data && chown -R app:app /app/data

USER app

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os; from urllib.request import urlopen; urlopen('http://127.0.0.1:' + os.environ.get('PORT','10000') + '/api/v1/health', timeout=3)"

CMD ["sh","-c","exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers ${WEB_CONCURRENCY:-2} --timeout 30 --access-logfile - --error-logfile - wsgi:app"]
