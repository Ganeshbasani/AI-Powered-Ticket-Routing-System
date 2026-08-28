# ============================================================
# Stage 1: Build frontend
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json ./
COPY frontend/build.mjs ./
COPY frontend/src ./src

RUN npm run build


# ============================================================
# Stage 2: Python application
# ============================================================
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

# Copy the REAL frontend build generated in stage 1
COPY --from=frontend-builder --chown=app:app /frontend/dist ./frontend/dist

# Verify frontend files exist during Docker build
RUN test -f /app/frontend/dist/index.html && \
    test -f /app/frontend/dist/app.js && \
    test -f /app/frontend/dist/style.css

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:5000/api/v1/health', timeout=3)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "wsgi:app"]
