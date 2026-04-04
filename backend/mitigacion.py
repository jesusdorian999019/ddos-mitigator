#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de mitigación usando ipset + nftables.
Interfaz de alto rendimiento para bloqueo automático de IPs maliciosas.
Requiere privilegios de root. Soporte persistencia JSON.
"""
import subprocess
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List
from backend.config import config

logging.basicConfig(level=config.get('log_level', 'INFO'))
logger = logging.getLogger(__name__)

class Mitigador:
    IPSET_NAME = 'ddos_blacklist'
    BLOQUEADOS_FILE = Path('data/bloqueados.json')
    
    def __init__(self):
        if os.geteuid() != 0:
            raise PermissionError("Mitigador requiere privilegios de root")
        self.BLOQUEADOS_FILE.parent.mkdir(exist_ok=True)
        self._verificar_dependencias()

    def _verificar_dependencias(self) -> None:
        """Verifica ipset y nftables disponibles."""
        try:
            subprocess.run(['ipset', 'list', self.IPSET_NAME], 
                         capture_output=True, check=True)
        except subprocess.CalledProcessError:
            raise RuntimeError(f"ipset {self.IPSET_NAME} no existe. Ejecuta setup.sh")

    def agregar_ip(self, ip: str, timeout: int = None) -> bool:
        """Agrega IP a blacklist con timeout opcional."""
        if ip in config.get('whitelist', []):
            logger.warning(f"IP {ip} en whitelist, no bloqueada")
            return False
        
        timeout_str = f" timeout {timeout}" if timeout else ""
        cmd = f"ipset add {self.IPSET_NAME} {ip}{timeout_str}"
        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            logger.info(f"Bloqueada IP: {ip} (timeout: {timeout}s)")
            self._guardar_bloqueadas()
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error bloqueando {ip}: {e}")
            return False

    def eliminar_ip(self, ip: str) -> bool:
        """Elimina IP de blacklist."""
        cmd = f"ipset del {self.IPSET_NAME} {ip}"
        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            logger.info(f"Desbloqueada IP: {ip}")
            self._guardar_bloqueadas()
            return True
        except subprocess.CalledProcessError:
            logger.warning(f"IP {ip} no estaba bloqueada")
            return False

    def listar_bloqueadas(self) -> List[str]:
        """Lista todas las IPs bloqueadas."""
        cmd = f"ipset list {self.IPSET_NAME} | grep -E '^([0-9]{{1,3}}\\\.){{3}}[0-9]{{1,3}}'"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
            return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        except subprocess.CalledProcessError:
            return []

    def esta_bloqueada(self, ip: str) -> bool:
        """Verifica si IP está en blacklist."""
        cmd = f"ipset test {self.IPSET_NAME} {ip}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False

    def _guardar_bloqueadas(self):
        """Persiste lista bloqueadas a JSON."""
        ips = self.listar_bloqueadas()
        data = {
            'timestamp': datetime.now().isoformat(),
            'ips': ips
        }
        try:
            self.BLOQUEADOS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Error guardando bloqueados: {e}")

    def cargar_bloqueadas(self):
        """Carga bloqueados persistidos."""
        if not self.BLOQUEADOS_FILE.exists():
            return
        try:
            data = json.loads(self.BLOQUEADOS_FILE.read_text())
            ips = data.get('ips', [])
            for ip in ips[:100]:  # Limit 100
                if not self.esta_bloqueada(ip):
                    self.agregar_ip(ip, 300)  # 5min default
            logger.info(f"Cargadas {len(ips)} bloqueados persistidos")
        except Exception as e:
            logger.error(f"Error cargando bloqueados: {e}")

# Instancia global (lazy init)
mitigador = None

def get_mitigador() -> 'Mitigador':
    global mitigador
    if mitigador is None:
        mitigador = Mitigador()
        mitigador.cargar_bloqueadas()  # Auto-load on init
    return mitigador

