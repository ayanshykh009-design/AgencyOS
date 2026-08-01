# AgencyOS frontend — DEVELOPMENT image.
# Production uses docker/frontend/Dockerfile.prod (multi-stage, Next.js standalone).
# Build context is the repo root:  docker build -f docker/frontend/Dockerfile .
FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better layer caching.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy application code (volume-mounted in dev; baked in for prod).
COPY frontend/ .

EXPOSE 3000

CMD ["npm", "run", "dev"]
