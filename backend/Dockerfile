FROM python:3.11-slim

WORKDIR /app

# Install curl for container HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Install production dependencies only
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and database migration configuration
COPY app/ ./app/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Ensure proper permissions for the storage and migrations directories
RUN mkdir -p /app/storage && chown -R appuser:appgroup /app/storage /app/alembic

USER appuser

EXPOSE 8000

# Container healthcheck targeting the GET /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
