#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de configuración centralizado para DDoS Mitigator.
Carga y valida parámetros desde config.yaml con valores por defecto.
Production-ready con validación robusta.
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from pathlib import Path
from backend.logger_config import LoggerConfig

logger = LoggerConfig.get_logger('backend.config')


class Config:
    """Gestor de configuración con validación y valores por defecto."""
    
    DEFAULTS = {
        'interfaz': 'eth0',
        'puerto_api': 8000,
        'baseline_pps': 100,
        'multiplicador_alerta': 3.0,
        'timeout_bloqueo': 600,
        'whitelist': [],
        'log_level': 'INFO',
        'log_dir': 'logs',
        'max_ips_bloqueadas': 1000,
        'max_alertas_cache': 10000,
        'data_path': 'data',
        'db_path': 'data/ddos.db',
        'enriquecimiento_activo': True,
        'max_bloqueos_ciclo': 20,
        'cache_enriquecimiento': 5000,
        'workers_enriquecimiento': 2,
        'timeout_enriquecimiento': 5.0,
        'rate_limit_api': 100,
        'modo_desarrollo': False,
    }
    
    VALIDADORES = {
        'baseline_pps': lambda x: isinstance(x, (int, float)) and x > 0,
        'multiplicador_alerta': lambda x: isinstance(x, (int, float)) and x > 1.0,
        'timeout_bloqueo': lambda x: isinstance(x, int) and x > 0,
        'puerto_api': lambda x: isinstance(x, int) and 1024 <= x <= 65535,
        'max_ips_bloqueadas': lambda x: isinstance(x, int) and x > 0,
        'max_alertas_cache': lambda x: isinstance(x, int) and x > 0,
    }
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        self.config_path = Path(config_path).resolve()
        self.data: Dict[str, Any] = {}
        self._load()
        self._validate()

    def _load(self) -> None:
        """Carga configuración desde YAML o usa defaults."""
        # Copiar defaults
        self.data = self.DEFAULTS.copy()
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f) or {}
                    if not isinstance(user_config, dict):
                        logger.warning("config.yaml inválido (no es dict), usando defaults")
                        user_config = {}
                    self.data.update(user_config)
                    logger.info(f"Config cargado desde {self.config_path}")
            except Exception as e:
                logger.error(f"Error leyendo config.yaml: {e}, usando defaults")
        else:
            logger.warning(f"config.yaml no encontrado en {self.config_path}")

    def _validate(self) -> None:
        """Valida valores de configuración."""
        for key, validator in self.VALIDADORES.items():
            value = self.data.get(key)
            if value is not None and not validator(value):
                logger.warning(f"Valor inválido para {key}: {value}, usando default")
                self.data[key] = self.DEFAULTS[key]
    
    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene valor con fallback a default."""
        return self.data.get(key, default or self.DEFAULTS.get(key))
    
    def update(self, key: str, value: Any) -> None:
        """Actualiza valor en runtime."""
        if key in self.VALIDADORES:
            if not self.VALIDADORES[key](value):
                raise ValueError(f"Valor inválido para {key}: {value}")
        self.data[key] = value
        logger.info(f"Config actualizado: {key}={value}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Retorna copia de configuración (sin sensibles)."""
        safe = self.data.copy()
        # Remover datos sensibles
        for sensitive_key in ['token', 'apikey', 'password', 'secret']:
            safe.pop(sensitive_key, None)
        return safe


# Instancia global singleton
_config_instance: Optional[Config] = None

def get_config() -> Config:
    """Factory singleton para Config."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
        logger.info(f"Config initializado: interfaz={_config_instance.get('interfaz')}")
    return _config_instance


# Legacy support
config = get_config()

