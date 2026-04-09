#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilidades compartidas: validación, decoradores, y helpers thread-safe.
"""
import re
import subprocess
import threading
import time
import functools
from typing import Optional, Callable, Any
from ipaddress import ip_address, ip_network, AddressValueError
from backend.logger_config import LoggerConfig

logger = LoggerConfig.get_logger('backend.utils')


# Validación de IPs
class IPValidator:
    """Validador robusto de IPs y redes."""
    
    # Regex para IPv4 simple (rápido)
    IPV4_REGEX = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
    # Regex para IPv6
    IPV6_REGEX = re.compile(r'^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4})$')
    
    @staticmethod
    def es_ipv4(ip: str) -> bool:
        """Valida IPv4."""
        try:
            return bool(IPValidator.IPV4_REGEX.match(ip)) and str(ip_address(ip).version) == '4'
        except (AddressValueError, ValueError):
            return False
    
    @staticmethod
    def es_ipv6(ip: str) -> bool:
        """Valida IPv6."""
        try:
            return str(ip_address(ip).version) == '6'
        except (AddressValueError, ValueError):
            return False
    
    @staticmethod
    def es_cidr(cidr: str) -> bool:
        """Valida CIDR."""
        try:
            ip_network(cidr, strict=False)
            return True
        except (AddressValueError, ValueError):
            return False
    
    @staticmethod
    def es_valida(ip: str) -> bool:
        """Acepta IPv4 o IPv6."""
        return IPValidator.es_ipv4(ip) or IPValidator.es_ipv6(ip)


# Thread safety
class ThreadSafeObject:
    """Objeto base con lock para acceso seguro."""
    
    def __init__(self):
        self._lock = threading.RLock()
    
    def with_lock(self, func: Callable, *args, **kwargs) -> Any:
        """Ejecuta función under lock."""
        with self._lock:
            return func(*args, **kwargs)


# Decoradores
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator con backoff exponencial."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    attempt += 1
                    if attempt < max_attempts:
                        logger.warning(f"{func.__name__} attempt {attempt} failed, retrying in {current_delay}s: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception or Exception(f"{func.__name__} failed after {max_attempts} attempts")
        return wrapper
    return decorator


def timing(func):
    """Timing decorator para profiling."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000  # ms
        if elapsed > 100:  # Log si > 100ms
            logger.debug(f"{func.__name__} took {elapsed:.2f}ms")
        return result
    return wrapper


def rate_limit(max_calls: int = 10, time_window: float = 1.0):
    """Rate limiter basado en tokens."""
    def decorator(func):
        tokens = max_calls
        last_update = time.time()
        lock = threading.Lock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal tokens, last_update
            
            with lock:
                now = time.time()
                elapsed = now - last_update
                # Recuperar tokens
                tokens = min(max_calls, tokens + elapsed * (max_calls / time_window))
                last_update = now
                
                if tokens >= 1:
                    tokens -= 1
                    return func(*args, **kwargs)
                else:
                    raise RuntimeError(f"Rate limit exceeded for {func.__name__}")
        return wrapper
    return decorator


# Helpers de sistema
def check_command_exists(cmd: str) -> bool:
    """Verifica si comando existe en sistema."""
    try:
        subprocess.run(['which', cmd], capture_output=True, check=True)
        return True
    except:
        return False


def run_command(cmd: list, check: bool = True) -> tuple[int, str, str]:
    """Ejecuta comando y retorna (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Command error: {e}")
        return 1, "", str(e)


# LRU Cache thread-safe
from collections import OrderedDict
class ThreadSafeLRUCache:
    """LRU cache thread-safe para enriquecimiento."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                # Mover a final (MRU)
                self.cache.move_to_end(key)
                return self.cache[key]
        return None
    
    def put(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            
            # Evict if needed
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
    
    def clear(self) -> None:
        with self.lock:
            self.cache.clear()
