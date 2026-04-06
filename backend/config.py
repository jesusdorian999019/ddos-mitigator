#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de configuración para DDoS Mitigator.
Carga parámetros desde config.yaml con valores por defecto.
"""
import yaml
import os
import logging
from typing import Dict, List, Any
from pathlib import Path

class Config:
    def __init__(self, config_path: str = None) -> None:
        # Usar ruta absoluta si no se proporciona
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        self.config_path = Path(config_path).resolve()
        self.data: Dict[str, Any] = {}
        self._cargar()

    def _cargar(self) -> None:
        """Carga configuración desde YAML o usa defaults."""
        import logging
        logger = logging.getLogger(__name__)
        
        defaults = {
            'interfaz': 'eth0',
            'baseline_pps': 100,  # Paquetes/segundo baseline
            'multiplicador_alerta': 3.0,  # Alerta si PPS > baseline * multiplicador
            'timeout_bloqueo': 600,  # Segundos
            'whitelist': [],  # IPs blancas
            'log_level': 'INFO',
            'max_ips_bloqueadas': 1000,
            'data_path': 'data',
            'enriquecimiento_activo': True,
            'max_bloqueos_ciclo': 20
        }
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f) or {}
                    if not isinstance(user_config, dict):
                        logger.warning(f"config.yaml inválido, usando defaults")
                        user_config = {}
                    defaults.update(user_config)
            except Exception as e:
                logger.warning(f"Error cargando config.yaml: {e}, usando defaults")
        else:
            logger.info(f"config.yaml no encontrado en {self.config_path}, usando defaults")
        
        self.data = defaults
        logger.info(f"Configuración cargada: interfaz={self.data['interfaz']}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

# Instancia global
config = Config()

