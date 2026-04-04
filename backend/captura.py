#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de captura de paquetes en tiempo real usando scapy.
Diseñado para alto rendimiento con threading y contadores atómicos.
"""
from scapy.all import sniff, IP, TCP, UDP, ICMP
from collections import defaultdict, deque
import threading
import time
from typing import Dict, Deque
from datetime import datetime, timedelta
from backend.config import config

# Ventana de tiempo para PPS (segundos)
VENTANA_TIEMPO = 5

class Capturador:
    def __init__(self):
        self.interfaz = config.get('interfaz')
        self.contadores: Dict[str, Deque[float]] = defaultdict(deque)
        self.lock = threading.RLock()
        self.pausado = False
        self.sniffer = None
        self.hilos_ventana = []

    def contar_paquete(self, pkt) -> None:
        """Cuenta paquete en contador correspondiente."""
        if self.pausado:
            return
            
        if IP in pkt:
            ip_src = pkt[IP].src
            timestamp = time.time()
            
            # Clasificación por protocolo
            proto_key = ip_src
            if TCP in pkt and pkt[TCP].flags & 0x02:  # SYN
                proto_key = f"{ip_src}:TCP_SYN"
            elif UDP in pkt:
                proto_key = f"{ip_src}:UDP"
            elif ICMP in pkt:
                proto_key = f"{ip_src}:ICMP"
            
            with self.lock:
                self.contadores[proto_key].append(timestamp)
                # Limpiar paquetes fuera de ventana
                cutoff = timestamp - VENTANA_TIEMPO
                while self.contadores[proto_key] and self.contadores[proto_key][0] < cutoff:
                    self.contadores[proto_key].popleft()

    def pps_por_ip(self, ip: str, segundos: int = VENTANA_TIEMPO) -> int:
        """Calcula PPS para IP específica."""
        total = 0
        cutoff = time.time() - segundos
        with self.lock:
            for key in list(self.contadores.keys()):
                if key.startswith(ip + ':') or key == ip:
                    while self.contadores[key] and self.contadores[key][0] < cutoff:
                        self.contadores[key].popleft()
                    total += len(self.contadores[key])
        return total // segundos

    def top_ips(self, n: int = 10) -> list:
        """IPs con más PPS."""
        stats = []
        cutoff = time.time() - VENTANA_TIEMPO
        with self.lock:
            for proto_key, times in self.contadores.items():
                ip = proto_key.split(':')[0]
                while times and times[0] < cutoff:
                    times.popleft()
                pps = len(times) // VENTANA_TIEMPO
                if pps > 0:
                    stats.append((ip, pps, proto_key.split(':')[1] if ':' in proto_key else 'OTRO'))
        # Ordenar por PPS desc
        stats.sort(key=lambda x: x[1], reverse=True)
        return stats[:n]

    def iniciar(self, callback_stats=None, filtro: str = None) -> None:
        """Inicia captura threaded."""
        filtro = filtro or f"not port 22 and not port 80"  # Evitar tráfico legítimo
        
        def packet_handler(pkt):
            self.contar_paquete(pkt)
            if callback_stats:
                callback_stats(self.top_ips(5))

        self.sniffer = sniff(iface=self.interfaz, prn=packet_handler, filter=filtro,
                            store=0, threaded=True)

    def pausar(self) -> None:
        self.pausado = True

    def reanudar(self) -> None:
        self.pausado = False

# Instancia global
capturador = Capturador()

