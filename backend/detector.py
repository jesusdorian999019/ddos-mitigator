#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de detección inteligente de ataques DoS/DDoS.
Baseline móvil dinámico con detección de anomalías thread-safe.
Production-ready con limits y cache LRU.
"""
import time
import threading
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from collections import deque
from backend.config import get_config
from backend.captura import capturador
from backend.logger_config import LoggerConfig
from backend.utils import ThreadSafeLRUCache, timing

logger = LoggerConfig.get_logger('backend.detector')

MAX_ALERTAS_CACHE = 10000
ANTI_SPAM_TTL = 60  # Segundos antes de re-enriquecer


class Detector:
    """Detector thread-safe con baseline adaptativo."""
    
    def __init__(self):
        self.config = get_config()
        self.baseline_historial: Dict[str, deque] = {}
        self.alertas_activas: Dict[str, Dict] = {}
        self.lock = threading.RLock()
        self.cache_enriquecimiento = ThreadSafeLRUCache(self.config.get('cache_enriquecimiento', 5000))
        self.stats = {
            'alertas_totales': 0,
            'anomalias_detectadas': 0,
            'falsos_positivos': 0,
        }

    @timing
    def actualizar_baseline(self, ip: str, pps_actual: int) -> float:
        """Calcula baseline móvil (media últimos 60s)."""
        with self.lock:
            if ip not in self.baseline_historial:
                self.baseline_historial[ip] = deque(maxlen=12)  # 12 * 5s = 60s
            
            self.baseline_historial[ip].append(pps_actual)
            
            if len(self.baseline_historial[ip]) == 0:
                return pps_actual
            
            baseline = sum(self.baseline_historial[ip]) / len(self.baseline_historial[ip])
            return baseline

    def detectar_anomalia(self, ip: str, pps: int, proto: str) -> Tuple[bool, str]:
        """Detecta anomalía basada en umbral dinámico."""
        try:
            baseline = self.actualizar_baseline(ip, pps)
            multiplicador = self.config.get('multiplicador_alerta', 3.0)
            umbral = baseline * multiplicador
            
            es_anomalia = pps > umbral
            
            if es_anomalia:
                tipo_ataque = self._clasificar_ataque(proto)
                razon = f"{tipo_ataque} (PPS: {pps}, umbral: {umbral:.1f})"
                self.stats['anomalias_detectadas'] += 1
                return True, razon
            
            return False, ""
        except Exception as e:
            logger.error(f"Error en detección: {e}", exc_info=True)
            return False, ""

    def _clasificar_ataque(self, proto: str) -> str:
        """Clasifica tipo de ataque por protocolo."""
        if 'TCP_SYN' in proto:
            return 'SYN Flood'
        elif 'UDP' in proto:
            return 'UDP Flood'
        elif 'ICMP' in proto:
            return 'ICMP Flood'
        return 'DoS Detectado'

    @timing
    def escanear_y_detectar(self) -> List[Dict]:
        """Escanea top IPs y detecta anomalías."""
        alertas = []
        top = capturador.top_ips(20)
        
        try:
            from backend.enriquecimiento import get_enriquecedor
            enriquecedor = get_enriquecedor()
        except ImportError:
            enriquecedor = None
        
        now = time.time()
        
        for ip, pps, proto in top:
            es_anomalia, razon = self.detectar_anomalia(ip, pps, proto)
            
            if es_anomalia:
                with self.lock:
                    # Obtener baseline actual
                    baseline = 0
                    if ip in self.baseline_historial and len(self.baseline_historial[ip]) > 0:
                        baseline = self.baseline_historial[ip][-1]
                    
                    alerta = {
                        'ip': ip,
                        'pps': pps,
                        'baseline': baseline,
                        'razon': razon,
                        'timestamp': datetime.now().isoformat(),
                        'proto': proto,
                    }
                
                alertas.append(alerta)
                
                # Enriquecer con anti-spam (LRU cache)
                if enriquecedor:
                    cache_key = f"{ip}:{proto}"
                    if self.cache_enriquecimiento.get(cache_key) is None:
                        self.cache_enriquecimiento.put(cache_key, now)
                        tipo = razon.split(' (')[0]
                        enriquecedor.agregar(ip, tipo, pps)
                
                # Actualizar alertas activas con límite
                with self.lock:
                    self.alertas_activas[ip] = alerta
                    self.stats['alertas_totales'] += 1
                    
                    # Evict si necesario
                    if len(self.alertas_activas) > MAX_ALERTAS_CACHE:
                        # Remover más antigua
                        oldest_ip = min(self.alertas_activas.keys(), 
                                      key=lambda k: self.alertas_activas[k].get('timestamp', ''))
                        del self.alertas_activas[oldest_ip]
        
        return alertas

    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas del detector."""
        with self.lock:
            return self.stats.copy()

    def limpiar_alertas_antiguas(self, max_edad_segundos: int = 300) -> None:
        """Limpia alertas antiguas (5 min por defecto)."""
        now = time.time()
        with self.lock:
            keys_to_remove = []
            for ip, alerta in self.alertas_activas.items():
                try:
                    timestamp = datetime.fromisoformat(alerta['timestamp'])
                    edad = (datetime.now() - timestamp).total_seconds()
                    if edad > max_edad_segundos:
                        keys_to_remove.append(ip)
                except Exception as e:
                    logger.debug(f"Error calculando edad de alerta: {e}")
            
            for ip in keys_to_remove:
                del self.alertas_activas[ip]
            
            if keys_to_remove:
                logger.info(f"Limpiadas {len(keys_to_remove)} alertas antiguas")


# Instancia global
detector = Detector()

