# AgencyOS backend — DEVELOPMENT image (hot reload).
# Production uses docker/backend/Dockerfile.prod (multi-stage, non-root).
# Build context is the repo root:  docker build -f docker/backend/Dockerfile .
FROM python:3.12-slim

# Python: don't write .pyc, run unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
