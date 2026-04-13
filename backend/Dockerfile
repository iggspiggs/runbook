FROM python:3.12-slim

# System dependencies
# gcc + libpq-dev are needed to compile psycopg2-binary from source if the
# binary wheel falls back, and are required by cryptography (python-jose).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Make the startup script executable
RUN chmod +x /app/start.sh

EXPOSE 8000

# Default CMD — overridden by docker-compose command directive
CMD ["/app/start.sh"]
