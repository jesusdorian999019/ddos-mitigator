FROM ubuntu:22.04

# Metadatos
LABEL maintainer="DDoS Mitigator"
LABEL version="2.0"

# Variables de entorno
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ipset \
    nftables \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root (opcional para dev)
RUN useradd -m -s /bin/bash mitigator || true

# Directorio de trabajo
WORKDIR /app

# Copiar código
COPY . .

# Crear venv e instalar deps
RUN python3.11 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Crear directorios necesarios
RUN mkdir -p data logs && chmod 777 data logs

# Setup script
RUN chmod +x scripts/setup.sh

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Puerto
EXPOSE 8000

# Default config (se puede sobrescribir con volumen)
RUN cp config.yaml config.yaml.example || echo "# Config example" > config.yaml.example

# Entrypoint
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0"]
CMD ["--port", "8000"]
