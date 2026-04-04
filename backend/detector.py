#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de detección inteligente de ataques DoS/DDoS.
Usa umbrales dinámicos basados en baseline móvil.
"""
import time
import logging
from typing import List, Dict, Tuple
from collections import deque
from backend.config import config
from backend.captura import capturador

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self):
        self.baseline_historial: Dict[str, deque] = {}  # IP -> deque PPS históricos
        self.alertas_activas: Dict[str, Dict] = {}  # IP -> info alerta
        self.lock = threading.RLock()

    def actualizar_baseline(self, ip: str, pps_actual: int) -> float:
        """Calcula baseline móvil (media últimos 60s)."""
        if ip not in self.baseline_historial:
            self.baseline_historial[ip] = deque(maxlen=12)  # 12 * 5s = 60s
        
        self.baseline_historial[ip].append(pps_actual)
        baseline = sum(self.baseline_historial[ip]) / len(self.baseline_historial[ip])
        return baseline

    def detectar_anomalia(self, ip: str, pps: int, proto: str) -> Tuple[bool, str]:
        """Detecta si PPS excede umbral dinámico."""
        baseline = self.actualizar_baseline(ip, pps)
        umbral = baseline * config.get('multiplicador_alerta', 3.0)
        
        if pps > umbral:
            tipo_ataque = self._clasificar_ataque(proto)
            return True, f"{tipo_ataque} (PPS: {pps}, umbral: {umbral:.1f})"
        return False, ""

    def _clasificar_ataque(self, proto: str) -> str:
        if 'TCP_SYN' in proto:
            return 'SYN Flood'
        elif 'UDP' in proto:
            return 'UDP Flood'
        elif 'ICMP' in proto:
            return 'ICMP Flood'
        return 'DoS Detectado'

    def escanear_y_detectar(self) -> List[Dict]:
        """Escanea top IPs y detecta anomalías. Integra enriquecimiento."""
        alertas = []
        top = capturador.top_ips(20)
        
        try:
            from backend.enriquecimiento import get_enriquecedor
            enriquecedor = get_enriquecedor()
        except ImportError:
            enriquecedor = None
            
        # Cache anti-spam enriquecimiento (TTL 60s)
        cache_ips = getattr(self, 'cache_ips', {})
        now = time.time()
        
        for ip, pps, proto in top:
            es_anomalia, razon = self.detectar_anomalia(ip, pps, proto)
            if es_anomalia:
                alerta = {
                    'ip': ip,
                    'pps': pps,
                    'baseline': self.baseline_historial.get(ip, deque([0]))[-1] if self.baseline_historial.get(ip) else 0,
                    'razon': razon,
                    'timestamp': datetime.now().isoformat()
                }
                # Enriquecer solo si no reciente (anti-spam)
                if enriquecedor and (ip not in cache_ips or now - cache_ips[ip] > 60):
                    cache_ips[ip] = now
                    tipo = razon.split(' (')[0]
                    enriquecedor.agregar(ip, tipo, pps)
                alertas.append(alerta)
                self.alertas_activas[ip] = alerta
        self.cache_ips = cache_ips  # Guardar estado
        return alertas

detector = Detector()


