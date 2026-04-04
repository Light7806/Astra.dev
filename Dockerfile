
# Dependency Hell - CI/CD OpenEnv Environment

FROM python:3.10-slim
# Set working directory
WORKDIR /app
# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*
# Copy requirements first (layer caching — faster rebuilds)
COPY requirements.txt .
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Copy the rest of the project
COPY . .
# Expose the port FastAPI runs on
EXPOSE 8000
# Health check so HF Space knows when the server is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
# Boot the FastAPI server (NOT the inference script)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]