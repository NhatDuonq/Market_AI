FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system utilities & Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt package.json package-lock.json ./
RUN pip install --no-cache-dir -r requirements.txt \
    && npm install --omit=dev

# Install Playwright chromium browser with OS dependencies
RUN playwright install --with-deps chromium

COPY . .

# Ensure persistent storage directories exist
RUN mkdir -p storage/snapshots/history storage/screenshots storage/ai_cache

EXPOSE 3000 5001

CMD ["node", "dashboard/server.js"]
