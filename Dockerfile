# AgriGrade - AI Onion Quality Inspection & Grading System
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system runtime dependencies for OpenCV and networking
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

# Create storage directories
RUN mkdir -p /app/storage/lots /app/storage/reports

# Run database seeder on container launch if DB does not exist
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Default start command
CMD ["sh", "-c", "python backend/seed.py && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
