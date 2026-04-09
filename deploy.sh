#!/bin/bash
# Deploy script para DDoS Mitigator
# Uso: sudo bash deploy.sh

set -euo pipefail

echo "=== DDoS Mitigator Deployment Script ==="

# Validar root
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] ERROR: Debe ejecutarse con sudo"
  exit 1
fi

# Variables
INSTALL_DIR="/opt/ddos-mitigator"
SERVICE_FILE="/etc/systemd/system/ddos-mitigator.service"
USER="ddos-mitigator"

# Crear usuario
if ! id "$USER" &>/dev/null ; then
    useradd -r -s /bin/bash "$USER" || true
    echo "[OK] Usuario creado: $USER"
fi

# Crear directorio de instalación
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Copiar código (assumir repo está en /tmp)
if [ -d "/tmp/ddos-mitigator" ]; then
    echo "[INFO] Copiando código desde /tmp..."
    cp -r /tmp/ddos-mitigator/* "$INSTALL_DIR/"
fi

# Setup venv
echo "[INFO] Configurando ambiente virtual..."
python3.11 -m venv venv || python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "[INFO] Instalando dependencias..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Ejecutar setup.sh
echo "[INFO] Ejecutando setup.sh..."
bash scripts/setup.sh

# Crear sistemd service
echo "[INFO] Creando systemd service..."
tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=DDoS Mitigator - Detección y Mitigación Automática
Documentation=https://github.com/user/ddos-mitigator
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Restart
Restart=always
RestartSec=10
StartLimitInterval=60s
StartLimitBurst=3

# Resource limits
MemoryLimit=2G
CPUQuota=200%

# Security
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=false
PrivateDevices=no
DevicePolicy=open

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ddos-mitigator

[Install]
WantedBy=multi-user.target
EOF

# Recargar systemd
systemctl daemon-reload
echo "[OK] Service instalado"

# Permisos
chown -R "$USER":"$USER" "$INSTALL_DIR" || chown -R root:root "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"/scripts/setup.sh

# Crear directorios de datos
mkdir -p "$INSTALL_DIR"/logs "$INSTALL_DIR"/data
chmod 755 "$INSTALL_DIR"/logs "$INSTALL_DIR"/data

# Habilitar y iniciar
echo "[INFO] Habilitando servicio..."
systemctl enable ddos-mitigator
systemctl start ddos-mitigator

# Status
echo ""
echo "[OK] Instalación completada!"
echo ""
echo "PROXIMOS PASOS:"
echo "1. Editar configuración:"
echo "   nano $INSTALL_DIR/config.yaml"
echo ""
echo "2. Ver status:"
echo "   systemctl status ddos-mitigator"
echo ""
echo "3. Ver logs:"
echo "   journalctl -u ddos-mitigator -f"
echo ""
echo "4. Acceder al panel:"
echo "   http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "5. Desinstalar:"
echo "   systemctl stop ddos-mitigator"
echo "   systemctl disable ddos-mitigator"
echo "   rm -rf $INSTALL_DIR $SERVICE_FILE"
echo ""
