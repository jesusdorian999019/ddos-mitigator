#!/bin/bash

# Script de instalación para DDoS Mitigator
# Debe ejecutarse como root

set -e

echo "=== Instalación de dependencias del sistema ==="
apt update
apt install -y ipset nftables python3-pip python3-venv scapy

echo "=== Configuración de Python ==="
cd $(dirname $0)/..
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Configuración de ipset ==="
ipset destroy ddos_blacklist 2>/dev/null || true
ipset create ddos_blacklist hash:ip timeout 600

echo "=== Configuración de nftables ==="
nft flush ruleset
nft add table inet ddos_filter
nft add chain inet ddos_filter input { type filter hook input priority 0 \\; policy accept \\; }
nft add chain inet ddos_filter forward { type filter hook forward priority 0 \\; policy accept \\; }
nft add set inet ddos_filter blacklist { type ipv4_addr \\; flags timeout \\; }
nft add rule inet ddos_filter input ip saddr @blacklist drop
nft add rule inet ddos_filter forward ip saddr @blacklist drop

mkdir -p data/
echo "=== Enriquecimiento GeoIP: Descarga manual ==="
echo "1. Regístrate gratis en https://dev.maxmind.com/geoip/geolite2-free-geolocation-data"
echo "2. Descarga GeoLite2-City.mmdb y GeoLite2-ASN.mmdb a ./data/"
echo "=== Verificaciones completadas ==="
echo "Para ejecutar: source venv/bin/activate &amp;&amp; sudo uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo "Panel web: http://localhost:8000"
echo "Logs forenses: data/logs.jsonl"
