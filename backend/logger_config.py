#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuración centralizada de logging con rotación automática.
Cumple con production-ready standards.
"""
import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class LoggerConfig:
    """Configurador centralizado de logging."""
    
    _initialized = False
    _loggers = {}
    
    # Níveles por módulo
    LEVELS = {
        'backend': logging.INFO,
        'backend.captura': logging.DEBUG,
        'backend.detector': logging.INFO,
        'backend.mitigacion': logging.INFO,
        'backend.enriquecimiento': logging.DEBUG,
        'uvicorn': logging.WARNING,
        'uvicorn.error': logging.ERROR,
    }
    
    @classmethod
    def setup(cls, log_dir: str = 'logs', level: str = 'INFO') -> None:
        """Configura logging centralizado con rotación."""
        if cls._initialized:
            return
        
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        # Formato completo
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler de archivo con rotación (10MB x 5 archivos)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / 'ddos_mitigator.log',
            maxBytes=10_000_000,
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        
        # Handler de console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Configurar loggers por módulo
        root_logger = logging.getLogger('backend')
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Aplicar niveles específicos
        for logger_name, log_level in cls.LEVELS.items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(log_level)
        
        cls._initialized = True
        logging.getLogger('backend').info("Logging system initialized")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Obtiene logger ya configurado."""
        if not cls._initialized:
            cls.setup()
        return logging.getLogger(name)
