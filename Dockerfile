FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV OPENAI_API_KEY=pollinations

# Set working directory
WORKDIR /app

# Install system dependencies for all 6 supported languages:
#   python       -> already in base image (python:3.11-slim)
#   javascript   -> nodejs
#   c            -> gcc
#   cpp          -> g++
#   java         -> default-jdk-headless (provides javac + java)
#   sql          -> Python's built-in sqlite3 module (no extra package needed)
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

# Create required directories; /tmp is writable by default on Railway
RUN mkdir -p /app/user_data/sessions /app/user_data/tmp

# Railway sets PORT env var; default to 5000
ENV PORT=5000
EXPOSE 5000

# Run with gunicorn for production
# gthread worker: each SSE stream holds one thread, not one whole worker process.
# --threads 16 lets 2 workers handle 32 concurrent SSE connections without queuing.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --worker-class gthread --workers 2 --threads 16 --timeout 120 --access-logfile - --error-logfile - app:app"]
