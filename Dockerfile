FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV OPENAI_API_KEY=pollinations

# Set working directory
WORKDIR /app

# Install system dependencies for code execution (all 6 supported languages)
# python: already in base image
# javascript: nodejs
# c: gcc
# cpp: g++
# java: default-jdk-headless (javac + java)
# sql: python sqlite3 module (built-in, no extra package needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    nodejs \
    default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories and ensure /tmp is writable for code execution
RUN mkdir -p /app/user_data/sessions /app/user_data/tmp \
    && chmod 1777 /tmp

# Railway sets PORT env var; default to 5000
ENV PORT=5000
EXPOSE 5000

# Run with gunicorn for production
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
