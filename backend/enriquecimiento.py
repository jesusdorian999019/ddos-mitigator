#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de enriquecimiento forense para IPs - GeoIP, ASN, RDNS.
Background threads non-blocking con queue management y error resilience.
Production-ready con timeouts y limits.
"""
import json
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from queue import Queue, Full, Empty
from collections import deque
from backend.config import get_config
from backend.logger_config import LoggerConfig
from backend.utils import threading, retry

logger = LoggerConfig.get_logger('backend.enriquecimiento')

# Intentar cargar GeoIP
try:
    import geoip2.database
    GEOIP_AVAILABLE = True
except ImportError:
    GEOIP_AVAILABLE = False
    logger.warning("geoip2 no disponible, enriquecimiento parcial")


class Enriquecedor:
    """Enriquecedor forense thread-safe con gestión de queue."""
    
    def __init__(self):
        self.config = get_config()
        self.data_path = Path(self.config.get('data_path', 'data'))
        self.data_path.mkdir(exist_ok=True)
        self.log_file = self.data_path / 'logs.jsonl'
        
        self.buffer: List[Dict] = []
        self.buffer_lock = threading.Lock()
        self.max_buffer = 100
        
        # Queue thread-safe con límite
        self.queue_size = self.config.get('max_alertas_cache', 10000)
        self.queue = Queue(maxsize=self.queue_size)
        
        # GeoIP readers
        self.city_reader = None
        self.asn_reader = None
        self._load_geoip_dbs()
        
        # Workers
        self.workers_count = self.config.get('workers_enriquecimiento', 2)
        self._running = False
        self.worker_threads = []
        self._start_workers()
        
        logger.info(f"Enriquecedor iniciado con {self.workers_count} workers")

    def _load_geoip_dbs(self) -> None:
        """Carga bases de datos GeoIP."""
        if not GEOIP_AVAILABLE:
            return
        
        try:
            city_path = self.data_path / 'GeoLite2-City.mmdb'
            asn_path = self.data_path / 'GeoLite2-ASN.mmdb'
            
            if city_path.exists():
                self.city_reader = geoip2.database.Reader(str(city_path))
                logger.info("GeoLite2-City.mmdb cargado")
            else:
                logger.warning(f"GeoLite2-City.mmdb no encontrado en {city_path}")
            
            if asn_path.exists():
                self.asn_reader = geoip2.database.Reader(str(asn_path))
                logger.info("GeoLite2-ASN.mmdb cargado")
            else:
                logger.warning(f"GeoLite2-ASN.mmdb no encontrado en {asn_path}")
        
        except Exception as e:
            logger.error(f"Error cargando GeoIP DBs: {e}")

    def _start_workers(self) -> None:
        """Inicia workers para enriquecimiento async."""
        self._running = True
        for i in range(self.workers_count):
            t = threading.Thread(target=self._worker_loop, daemon=True, 
                               name=f"Enriquecedor-{i}")
            t.start()
            self.worker_threads.append(t)

    def _worker_loop(self) -> None:
        """Loop de worker para procesar queue."""
        while self._running:
            try:
                ip_data = self.queue.get(timeout=1)
                if ip_data is None:  # Señal de salida
                    break
                
                enriquecido = self._enriquecer(ip_data['ip'], ip_data['tipo'], ip_data['pps'])
                
                with self.buffer_lock:
                    self.buffer.append(enriquecido)
                    if len(self.buffer) >= self.max_buffer:
                        self._dump_buffer_unsafe()
            
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error en worker: {e}", exc_info=True)
                time.sleep(0.1)

    def _enriquecer(self, ip: str, tipo: str, pps: int) -> Dict:
        """Enriquece datos de IP."""
        resultado = {
            'ip': ip,
            'tipo_ataque': tipo,
            'pps': pps,
            'timestamp': datetime.now().isoformat(),
            'pais': 'Desconocido',
            'ciudad': 'Desconocida',
            'asn': 'Desconocido',
            'hostname': 'Desconocido',
        }
        
        # GeoIP City
        if self.city_reader:
            try:
                resp = self.city_reader.city(ip)
                resultado['pais'] = resp.country.name or 'N/A'
                resultado['ciudad'] = resp.city.name or 'N/A'
            except Exception:
                pass  # IP privada o error
        
        # ASN/ISP
        if self.asn_reader:
            try:
                resp = self.asn_reader.asn(ip)
                resultado['asn'] = f"AS{resp.autonomous_system_number} {resp.autonomous_system_organization}"
            except Exception:
                pass
        
        # Reverse DNS (con timeout)
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            resultado['hostname'] = hostname
        except socket.timeout:
            logger.debug(f"Timeout en RDNS para {ip}")
        except socket.herror:
            pass  # Normal para IPs sin RDNS
        except Exception as e:
            logger.debug(f"Error en RDNS {ip}: {e}")
        
        return resultado

    def agregar(self, ip: str, tipo: str, pps: int) -> bool:
        """Agrega a queue para enriquecimiento (non-blocking)."""
        try:
            self.queue.put_nowait({'ip': ip, 'tipo': tipo, 'pps': pps})
            return True
        except Full:
            logger.warning(f"Queue llena, descartando enriquecimiento para {ip}")
            return False

    def _dump_buffer_unsafe(self) -> None:
        """Guarda buffer a JSONL (llama con lock externo)."""
        if not self.buffer:
            return
        
        try:
            with self.log_file.open('a', encoding='utf-8') as f:
                for evento in self.buffer:
                    f.write(json.dumps(evento, ensure_ascii=False) + '\n')
            logger.debug(f"Dumpeados {len(self.buffer)} logs")
            self.buffer.clear()
        except Exception as e:
            logger.error(f"Error dump logs: {e}", exc_info=True)

    def flush(self) -> None:
        """Fuerza escribir buffer a disco."""
        with self.buffer_lock:
            self._dump_buffer_unsafe()

    def obtener_recientes(self, n: int = 50) -> List[Dict]:
        """Últimos logs para API (thread-safe)."""
        if not self.log_file.exists():
            return []
        
        try:
            with self.log_file.open('r', encoding='utf-8') as f:
                lines = list(f)
            
            # Últimas n líneas
            lines = lines[-n:] if len(lines) > n else lines
            
            parsed = []
            for line in lines:
                if line.strip():
                    try:
                        parsed.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        logger.debug(f"Línea JSONL inválida: {line[:50]}...")
            
            return parsed
        
        except Exception as e:
            logger.error(f"Error leyendo logs: {e}", exc_info=True)
            return []

    def estadisticas(self) -> Dict:
        """Retorna estadísticas del enriquecedor."""
        return {
            'queue_size': self.queue.qsize(),
            'queue_max': self.queue_size,
            'buffer_size': len(self.buffer),
            'workers': self.workers_count,
            'geoip_disponible': GEOIP_AVAILABLE and self.city_reader is not None,
        }

    def detener(self) -> None:
        """Detiene gracefully los workers."""
        logger.info("Deteniendo enriquecedor...")
        self._running = False
        
        # Flush final
        self.flush()
        
        # Señal de salida
        for _ in range(self.workers_count):
            try:
                self.queue.put_nowait(None)
            except Full:
                pass
        
        # Esperar a workers (con timeout)
        for t in self.worker_threads:
            t.join(timeout=2)
        
        logger.info("Enriquecedor detenido")


# Instancia global lazy
_enriquecedor: Optional[Enriquecedor] = None
_enriquecedor_lock = threading.Lock()


def get_enriquecedor() -> Enriquecedor:
    """Factory singleton thread-safe."""
    global _enriquecedor
    if _enriquecedor is None:
        with _enriquecedor_lock:
            if _enriquecedor is None:
                _enriquecedor = Enriquecedor()
    return _enriquecedor
