#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de captura de paquetes en tiempo real usando Scapy.
Thread-safe, con graceful shutdown y manejo robusto de errores.
Optimizado para alto rendimiento: O(1) lookups.
"""
import threading
import time
import logging
from typing import Dict, List, Deque, Optional, Callable, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
from scapy.all import sniff, IP, TCP, UDP, ICMP
from backend.config import get_config
from backend.logger_config import LoggerConfig
from backend.utils import timing

logger = LoggerConfig.get_logger('backend.captura')

# Ventana de tiempo para PPS (segundos)
VENTANA_TIEMPO = 5
MAX_VENTANA_ITEMS = 100_000  # Límite para evitar memory leak


class Capturador:
    """Capturador thread-safe con limpieza automática."""
    
    def __init__(self):
        self.config = get_config()
        self.interfaz = self.config.get('interfaz')
        self.contadores: Dict[str, Deque[float]] = defaultdict(deque)
        self.lock = threading.RLock()
        self.pausado = False
        self.sniffer = None
        self.sniffer_thread = None
        self._running = False
        self.stats = {
            'paquetes_capturados': 0,
            'paquetes_dropeados': 0,
            'ips_unicas': 0,
            'ultimo_paquete': 0.0,
        }

    @timing
    def contar_paquete(self, pkt) -> None:
        """Cuenta paquete de forma thread-safe."""
        if self.pausado or self._running is False:
            return
        
        try:
            if IP not in pkt:
                return
            
            ip_src = pkt[IP].src
            timestamp = time.time()
            
            # Clasificación por protocolo (5-tuple rápido)
            proto_key = ip_src
            if TCP in pkt:
                if pkt[TCP].flags & 0x02:  # SYN
                    proto_key = f"{ip_src}:TCP_SYN"
            elif UDP in pkt:
                proto_key = f"{ip_src}:UDP"
            elif ICMP in pkt:
                proto_key = f"{ip_src}:ICMP"
            
            with self.lock:
                # Prevenir memory leak
                if len(self.contadores) > MAX_VENTANA_ITEMS:
                    logger.warning(f"Límite de contadores alcanzado ({MAX_VENTANA_ITEMS}), limpiando")
                    self._limpiar_contadores_unsafe()
                
                self.contadores[proto_key].append(timestamp)
                self.stats['paquetes_capturados'] += 1
                self.stats['ips_unicas'] = len(self.contadores)
                self.stats['ultimo_paquete'] = timestamp
                
                # Limpiar paquetes fuera de ventana (sliding window)
                cutoff = timestamp - VENTANA_TIEMPO
                while self.contadores[proto_key] and self.contadores[proto_key][0] < cutoff:
                    self.contadores[proto_key].popleft()
        
        except Exception as e:
            logger.error(f"Error procesando paquete: {e}", exc_info=True)

    def pps_por_ip(self, ip: str, segundos: int = VENTANA_TIEMPO) -> int:
        """Calcula PPS para IP específica."""
        if segundos <= 0:
            return 0
        
        total = 0
        cutoff = time.time() - segundos
        
        try:
            with self.lock:
                for key in list(self.contadores.keys()):
                    if key.startswith(f"{ip}:") or key == ip:
                        # Limpiar outdated
                        while self.contadores[key] and self.contadores[key][0] < cutoff:
                            self.contadores[key].popleft()
                        total += len(self.contadores[key])
            
            return max(1, total // segundos)
        except Exception as e:
            logger.error(f"Error calculando PPS para {ip}: {e}")
            return 1

    @timing
    def top_ips(self, n: int = 10) -> List[Tuple[str, int, str]]:
        """Retorna top N IPs por PPS."""
        try:
            stats = []
            cutoff = time.time() - VENTANA_TIEMPO
            
            with self.lock:
                for proto_key, times in self.contadores.items():
                    # Limpar outdated en-line
                    while times and times[0] < cutoff:
                        times.popleft()
                    
                    pps = len(times) // VENTANA_TIEMPO if len(times) > 0 else 0
                    if pps > 0:
                        ip = proto_key.split(':')[0]
                        proto = proto_key.split(':')[1] if ':' in proto_key else 'OTRO'
                        stats.append((ip, pps, proto))
            
            # Ordenar por PPS descendente
            stats.sort(key=lambda x: x[1], reverse=True)
            return stats[:n]
        
        except Exception as e:
            logger.error(f"Error calculando top IPs: {e}", exc_info=True)
            return []

    def _limpiar_contadores_unsafe(self) -> None:
        """Limpia contadores viejos (usa lock externo)."""
        cutoff = time.time() - VENTANA_TIEMPO * 3  # 3x ventana
        for key in list(self.contadores.keys()):
            while self.contadores[key] and self.contadores[key][0] < cutoff:
                self.contadores[key].popleft()
            if not self.contadores[key]:
                del self.contadores[key]

    def iniciar(self, callback_stats: Optional[Callable] = None, filtro: str = None) -> None:
        """Inicia captura en thread separado."""
        if self._running:
            logger.warning("Captura ya está corriendo")
            return
        
        if not self.interfaz:
            raise ValueError("Interfaz no configurada")
        
        filtro = filtro or "not port 22 and not port 443"  # Evitar SSH/HTTPS legítimo
        self._running = True
        
        def packet_handler(pkt):
            try:
                self.contar_paquete(pkt)
                if callback_stats and self.stats['paquetes_capturados'] % 1000 == 0:
                    callback_stats(self.top_ips(5))
            except Exception as e:
                logger.warning(f"Error en handler: {e}")

        def sniffer_wrapper():
            try:
                logger.info(f"Iniciando captura en {self.interfaz} con filtro: {filtro}")
                sniff(iface=self.interfaz, prn=packet_handler, filter=filtro,
                      store=False, threaded=False)
            except PermissionError:
                logger.error("ERROR: Requiere privilegios de root para sniffing")
            except Exception as e:
                logger.error(f"Error en captura: {e}", exc_info=True)
            finally:
                self._running = False

        # Thread daemon para captura
        self.sniffer_thread = threading.Thread(target=sniffer_wrapper, daemon=True, name="Capturador")
        self.sniffer_thread.start()
        logger.info("Thread de captura iniciado")

    def pausar(self) -> None:
        """Pausa captura sin parar thread."""
        self.pausado = True
        logger.info("Captura pausada")

    def reanudar(self) -> None:
        """Reanuda captura."""
        self.pausado = False
        logger.info("Captura reanudada")

    def detener(self) -> None:
        """Detiene captura gracefully."""
        self._running = False
        self.pausado = True
        logger.info("Captura detenida")

    def estadisticas(self) -> Dict:
        """Retorna estadísticas de captura."""
        with self.lock:
            return self.stats.copy()

    def limpiar(self) -> None:
        """Limpia todos los contadores."""
        with self.lock:
            self.contadores.clear()
            logger.info("Contadores limpiados")


# Instancia global
capturador = Capturador()

