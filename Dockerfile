# Kisan Setu — AI Onion Grading System
# Smart India Hackathon 2026
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MOCK_MODEL=true \
    SMS_MOCK=true

WORKDIR /app

# Install OpenCV system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend/ /app/backend/
COPY ml/ /app/ml/
COPY docs/ /app/docs/
COPY .env.example /app/.env.example
COPY start.sh /app/start.sh

# Create persistent storage directories
RUN mkdir -p /app/storage/lots /app/storage/reports \
    && chmod +x /app/start.sh

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["/app/start.sh"]
