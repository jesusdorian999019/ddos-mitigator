#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de configuración para DDoS Mitigator.
Carga parámetros desde config.yaml con valores por defecto.
"""
import yaml
import os
from typing import Dict, List, Any
from pathlib import Path

class Config:
    def __init__(self, config_path: str = 'config.yaml') -> None:
        self.config_path = Path(config_path)
        self.data: Dict[str, Any] = {}
        self._cargar()

    def _cargar(self) -> None:
        """Carga configuración desde YAML o usa defaults."""
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
            with open(self.config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f) or {}
                defaults.update(user_config)
        
        self.data = defaults
        print(f"Configuración cargada: interfaz={self.data['interfaz']}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

# Instancia global
config = Config()

