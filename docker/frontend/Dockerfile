# AgencyOS frontend image (dev-oriented).
# Build context is the repo root:  docker build -f docker/frontend/Dockerfile .
# NOTE: for production, add a multi-stage build (next build + standalone).
FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better layer caching.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy application code (volume-mounted in dev; baked in for prod).
COPY frontend/ .

EXPOSE 3000

CMD ["npm", "run", "dev"]
