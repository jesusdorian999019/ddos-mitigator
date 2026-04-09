#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de mitigación usando ipset + nftables.
Interfaz thread-safe para bloqueo automático de IPs maliciosas.
Production-ready con persistencia, validación robusta y graceful error handling.
"""
import subprocess
import os
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from backend.config import get_config
from backend.logger_config import LoggerConfig
from backend.utils import IPValidator, retry, run_command

logger = LoggerConfig.get_logger('backend.mitigacion')


class Mitigador:
    """Mitigador thread-safe con persistencia y validación robusta."""
    
    IPSET_NAME = 'ddos_blacklist'
    BLOQUEADOS_FILE = Path('data/bloqueados.json')
    
    def __init__(self):
        self.config = get_config()
        self.lock = threading.RLock()
        self.bloqueadas = set()  # Cache en memoria
        
        # Crear dir
        self.BLOQUEADOS_FILE.parent.mkdir(exist_ok=True)
        
        # Verificar dependencias
        try:
            self._verificar_dependencias()
        except Exception as e:
            logger.warning(f"Verificación de dependencias falló: {e}. Mitigación deshabilitada (Windows OK)")
            self._enabled = False
        else:
            self._enabled = True
            # Cargar persistidas
            self.cargar_bloqueadas()

    def _verificar_dependencias(self) -> None:
        """Verifica ipset y nftables en Linux."""
        import platform
        if platform.system() == 'Windows':
            logger.warning("Sistema Windows detectado - mitigación no disponible")
            return
        
        # Verificar ipset
        code, _, stderr = run_command(['ipset', 'list', self.IPSET_NAME])
        if code != 0:
            if 'does not exist' in stderr or 'No such file' in stderr:
                raise RuntimeError(f"ipset '{self.IPSET_NAME}' no existe. Ejecuta setup.sh")
            raise RuntimeError(f"Error verificando ipset: {stderr}")

    def _validar_ip_robusta(self, ip: str) -> bool:
        """Valida IP robustamente."""
        if not isinstance(ip, str):
            return False
        ip = ip.strip()
        return IPValidator.es_valida(ip)

    @retry(max_attempts=3, delay=0.5)
    def agregar_ip(self, ip: str, timeout: Optional[int] = None) -> bool:
        """Agrega IP a blacklist con reintentos."""
        # Validación
        if not self._validar_ip_robusta(ip):
            logger.error(f"IP inválida: {ip}")
            return False
        
        # Whitelist check
        whitelist = self.config.get('whitelist', [])
        if ip in whitelist:
            logger.info(f"IP {ip} está en whitelist, no bloqueada")
            return False
        
        # Check duplicados
        with self.lock:
            if ip in self.bloqueadas:
                logger.debug(f"IP {ip} ya bloqueada")
                return True
        
        if not self._enabled:
            logger.warning("Mitigación deshabilitada, no se bloquea")
            return False
        
        try:
            timeout = timeout or self.config.get('timeout_bloqueo', 600)
            cmd = ['ipset', 'add', self.IPSET_NAME, ip, 'timeout', str(timeout)]
            
            code, stdout, stderr = run_command(cmd)
            
            if code != 0:
                # Ya existe es OK
                if 'already' in stderr or 'exists' in stderr:
                    logger.debug(f"IP {ip} ya existía en ipset")
                else:
                    logger.error(f"Error bloqueando {ip}: {stderr}")
                    return False
            
            with self.lock:
                self.bloqueadas.add(ip)
            
            logger.info(f"Bloqueada IP: {ip} (timeout: {timeout}s)")
            self._guardar_bloqueadas()
            return True
        
        except Exception as e:
            logger.error(f"Error bloqueando {ip}: {e}", exc_info=True)
            raise  # Para retry

    def eliminar_ip(self, ip: str) -> bool:
        """Elimina IP de blacklist."""
        if not self._validar_ip_robusta(ip):
            logger.error(f"IP inválida: {ip}")
            return False
        
        if not self._enabled:
            logger.warning("Mitigación deshabilitada, no se desbloquea")
            return False
        
        try:
            cmd = ['ipset', 'del', self.IPSET_NAME, ip]
            code, _, stderr = run_command(cmd)
            
            if code == 0:
                with self.lock:
                    self.bloqueadas.discard(ip)
                logger.info(f"Desbloqueada IP: {ip}")
                self._guardar_bloqueadas()
                return True
            else:
                if 'not' in stderr.lower() and 'found' in stderr.lower():
                    logger.debug(f"IP {ip} no estaba bloqueada")
                    return True
                logger.error(f"Error desbloqueando {ip}: {stderr}")
                return False
        
        except Exception as e:
            logger.error(f"Error eliminando {ip}: {e}", exc_info=True)
            return False

    def listar_bloqueadas(self) -> List[str]:
        """Lista todas las IPs bloqueadas."""
        with self.lock:
            return list(self.bloqueadas)

    def esta_bloqueada(self, ip: str) -> bool:
        """Comprueba si IP está bloqueada."""
        if not self._validar_ip_robusta(ip):
            return False
        with self.lock:
            return ip in self.bloqueadas

    def _guardar_bloqueadas(self) -> None:
        """Persiste lista a JSON."""
        try:
            with self.lock:
                ips_list = list(self.bloqueadas)
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'cantidad': len(ips_list),
                'ips': ips_list
            }
            
            # Escribir a temp primero
            temp_file = self.BLOQUEADOS_FILE.with_suffix('.json.tmp')
            with temp_file.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.BLOQUEADOS_FILE)
            logger.debug(f"Persistidas {len(ips_list)} IPs bloqueadas")
        
        except Exception as e:
            logger.error(f"Error guardando bloqueados: {e}", exc_info=True)

    def cargar_bloqueadas(self) -> None:
        """Carga bloqueados persistidos."""
        if not self.BLOQUEADOS_FILE.exists():
            return
        
        try:
            with self.BLOQUEADOS_FILE.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            ips = data.get('ips', [])
            limit = self.config.get('max_ips_bloqueadas', 1000)
            ips = ips[:limit]
            
            with self.lock:
                for ip in ips:
                    if self._validar_ip_robusta(ip):
                        self.bloqueadas.add(ip)
            
            logger.info(f"Cargadas {len(self.bloqueadas)} IPs bloqueadas persistidas")
        
        except Exception as e:
            logger.error(f"Error cargando bloqueados: {e}", exc_info=True)

    def limpiar_todo(self) -> bool:
        """Limpia toda la blacklist."""
        if not self._enabled:
            return False
        
        try:
            code, _, stderr = run_command(['ipset', 'flush', self.IPSET_NAME])
            if code == 0:
                with self.lock:
                    self.bloqueadas.clear()
                logger.warning("Blacklist limpiada completamente")
                self._guardar_bloqueadas()
                return True
            else:
                logger.error(f"Error limpiando blacklist: {stderr}")
                return False
        except Exception as e:
            logger.error(f"Error en limpiar: {e}", exc_info=True)
            return False

    def estadisticas(self) -> Dict:
        """Retorna estadísticas de mitigación."""
        with self.lock:
            return {
                'ips_bloqueadas': len(self.bloqueadas),
                'max_bloqueables': self.config.get('max_ips_bloqueadas', 1000),
                'mitigacion_habilitada': self._enabled,
            }


# Instancia global (lazy init)
_mitigador = None
_mitigador_lock = threading.Lock()


def get_mitigador() -> Mitigador:
    """Factory singleton thread-safe."""
    global _mitigador
    if _mitigador is None:
        with _mitigador_lock:
            if _mitigador is None:
                _mitigador = Mitigador()
                logger.info("Mitigador inicializado")
    return _mitigador
    return mitigador

