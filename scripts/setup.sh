#!/bin/bash

# Script de instalación robusta para DDoS Mitigator

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Validar root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Ejecuta como root: sudo ./scripts/setup.sh"
  exit 1
fi

# Non-interactive
export DEBIAN_FRONTEND=noninteractive

# Logging
exec > >(tee setup.log) 2>&1

echo "=== DDoS Mitigator Setup (v2.0) ==="

# Validar requirements.txt
if [ ! -f "requirements.txt" ]; then
  echo "ERROR: Falta requirements.txt"
  exit 1
fi

echo "=== Instalando dependencias ==="
apt update
apt install -y ipset nftables python3-pip python3-venv

echo "=== Configurando entorno Python ==="
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Configurando ipset ==="
ipset destroy ddos_blacklist 2>/dev/null || true
ipset create ddos_blacklist hash:ip timeout 600

echo "=== Configurando nftables ==="
nft delete table inet ddos_filter 2>/dev/null || true
nft add table inet ddos_filter
nft add chain inet ddos_filter input { type filter hook input priority 0 \; policy accept \; }
nft add set inet ddos_filter blacklist { type ipv4_addr \; flags timeout \; }
nft add rule inet ddos_filter input ip saddr @blacklist drop

echo "=== Setup completado ==="
echo "Para ejecutar:"
echo "source venv/bin/activate"
echo "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"