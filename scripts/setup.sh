#!/bin/bash
# Setup script robusto para DDoS Mitigator
# Instala dependencias, configura ipset/nftables, prepara ambiente

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Funciones
log() { echo "[OK] $@"; }
warn() { echo "[WARN] $@"; }
error() { echo "[ERROR] ERROR: $@" >&2; exit 1; }

# ============ Validaciones ============
log "Validando requisitos..."

# Root check
if [ "$EUID" -ne 0 ]; then
  error "Debe ejecutarse con sudo"
fi

# Sistema operativo
if ! grep -qE "Ubuntu|Debian" /etc/os-release; then
  warn "Sistema no es Debian/Ubuntu - continuando con precaución"
fi

# Archivos necesarios
[ -f "requirements.txt" ] || error "No encontrado: requirements.txt"
[ -f "config.yaml" ] || warn "No encontrado: config.yaml (se creará)"

log "Plataforma detectada: $(lsb_release -d 2>/dev/null | cut -f2 || uname -s)"

# ============ Instalación de Dependencias ============
log "Actualizando repositorios..."
apt-get update || warn "apt update fallido"

log "Instalando dependencias del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y \
  python3-pip \
  python3-venv \
  ipset \
  nftables \
  curl \
  wget \
  net-tools \
  ca-certificates \
  || warn "Algunas dependencias pueden no haberse instalado"

log "Python version: $(python3 --version)"
log "ipset version: $(ipset --version 2>/dev/null || echo 'no detectado')"
log "nftables version: $(nft --version 2>/dev/null || echo 'no detectado')"

# ============ Virtual Environment ============
log "Configurando entorno virtual..."
if [ ! -d "venv" ]; then
  python3 -m venv venv
  log "Venv creado"
else
  log "Venv ya existe"
fi

# Activar
source venv/bin/activate

# Actualizar pip
log "Actualizando pip..."
pip install --upgrade pip setuptools wheel

# Instalar requirements
log "Instalando dependencias Python..."
pip install -r requirements.txt || error "pip install falló"

# ============ Configuración ipset ============
log "Configurando ipset..."

IPSET_NAME="ddos_blacklist"

# Limpiar si existe
if ipset list "$IPSET_NAME" &>/dev/null; then
  warn "ipset '$IPSET_NAME' ya existe, reemplazando..."
  ipset flush "$IPSET_NAME" || ipset destroy "$IPSET_NAME" && sleep 1
fi

# Crear ipset
ipset create "$IPSET_NAME" hash:ip timeout 600 || error "No se pudo crear ipset"
log "ipset '$IPSET_NAME' creado (timeout: 600s)"

# ============ Configuración nftables ============
log "Configurando nftables..."

TABLE_NAME="ddos_filter"

# Limpiar si existe
if nft list table inet "$TABLE_NAME" &>/dev/null 2>&1; then
  warn "Tabla nftables '$TABLE_NAME' existe, eliminando..."
  nft delete table inet "$TABLE_NAME" || true
  sleep 1
fi

# Crear tabla y reglas
nft add table inet "$TABLE_NAME" || error "No se pudo crear tabla nftables"
nft add chain inet "$TABLE_NAME" input { type filter hook input priority 0\; policy accept\; } || true
nft add rule inet "$TABLE_NAME" input ip saddr @"$IPSET_NAME" drop || true

log "Tabla nftables '$TABLE_NAME' configurada"
log "Regla: DROP de IPs en ipset"

# ============ Directorios Y Permisos ============
log "Creando directorios..."
mkdir -p data logs frontend

# Descargar GeoIP DBs (opcional)
log "Nota: Descargar bases de datos GeoIP:"
echo "  - Ir a https://www.maxmind.com/en/geoip2/geolite2"
echo "  - Registrarse (gratis)"
echo "  - Descargar GeoLite2-City.mmdb y GeoLite2-ASN.mmdb"
echo "  - Copiar a: $(pwd)/data/"

# ============ Config por defecto ============
if [ ! -f "config.yaml" ]; then
  log "Creando config.yaml por defecto..."
  cat > config.yaml <<'EOF'
interfaz: eth0
baseline_pps: 100
multiplicador_alerta: 3.0
timeout_bloqueo: 600
whitelist:
  - 127.0.0.1
log_level: INFO
max_ips_bloqueadas: 1000
data_path: data
enriquecimiento_activo: true
max_bloqueos_ciclo: 20
EOF
  log "config.yaml creado (editar según necesidad)"
fi

# ============ Verificación ============
log "Verificando instalación..."

# Test Python
"$PROJECT_DIR/venv/bin/python" -c "import fastapi, scapy, yaml; print('[OK] Dependencias Python OK')" || warn "Validación Python parcial"

# Test ipset
if ipset test "ddos_blacklist" 127.0.0.1 2>/dev/null; then
  log "ipset funcional"
else
  warn "ipset test fallido (puede ser normal si la IP no existe)"
fi

# Test nftables
if nft list table inet ddos_filter &>/dev/null; then
  log "nftables funcional"
else
  error "nftables no está configurado correctamente"
fi

# ============ Final ============
echo ""
log "=== Setup completado exitosamente ==="
echo ""
echo "PROXIMOS PASOS:"
echo ""
echo "1. Editar configuración:"
echo "   nano config.yaml"
echo ""
echo "2. Iniciar aplicación:"
echo "   source venv/bin/activate"
echo "   sudo ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "3. O usar script de deploy:"
echo "   sudo bash deploy.sh"
echo ""
echo "4. Abrir panel web:"
echo "   http://localhost:8000"
echo ""
echo "IMPORTANTE:"
echo "   - Editar config.yaml (interfaz, whitelist)"
echo "   - Ejecutar con 'sudo' para captura de paquetes"
echo "   - Descargar GeoIP DBs si se usa enriquecimiento"
echo ""
