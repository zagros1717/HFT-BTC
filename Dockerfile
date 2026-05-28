FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1 is needed by xgboost on slim images.
# curl is useful for container health/debug checks.
# supervisor runs the recorder and dashboard in parallel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

# Keep the container non-trading/research-only by default.
# The code also enforces execution_enabled: false in config/config.yaml.

# Create supervisor config directory
RUN mkdir -p /etc/supervisor/conf.d

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/supervisord.conf

# Expose Streamlit port
EXPOSE 8501

# Run supervisor to manage both recorder and dashboard
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]

