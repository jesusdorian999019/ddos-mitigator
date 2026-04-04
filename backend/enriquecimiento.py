#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de enriquecimiento forense para IPs sospechosas.
Ejecuta en background: GeoIP, ASN, RDNS. Logs a JSONL.
No bloquea detección principal.
"""
import json
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from queue import Queue
import geoip2.database
from backend.config import config

class Enriquecedor:
    def __init__(self):
        self.data_path = Path(config.get('data_path', 'data'))
        self.data_path.mkdir(exist_ok=True)
        self.log_file = self.data_path / 'logs.jsonl'
        self.buffer: List[Dict] = []
        self.max_buffer = 100
        self.lock = threading.RLock()
        self.queue = Queue()
        
        # Cargar GeoIP DBs
        self.city_reader = None
        self.asn_reader = None
        try:
            self.city_reader = geoip2.database.Reader(self.data_path / 'GeoLite2-City.mmdb')
            self.asn_reader = geoip2.database.Reader(self.data_path / 'GeoLite2-ASN.mmdb')
        except Exception as e:
            print(f"Advertencia: GeoIP DBs no cargadas ({e}). Descarga manual.")
        
        # Thread para procesamiento background
        self.worker_thread = threading.Thread(target=self._procesar_queue, daemon=True)
        self.worker_thread.start()
        
        print("Enriquecedor iniciado")

    def _procesar_queue(self):
        """Thread worker para enriquecimiento async."""
        while True:
            try:
                ip_data = self.queue.get(timeout=1)
                enriquecido = self._enriquecer(ip_data['ip'], ip_data['tipo'], ip_data['pps'])
                with self.lock:
                    self.buffer.append(enriquecido)
                    if len(self.buffer) >= self.max_buffer:
                        self._dump_buffer()
            except:
                time.sleep(0.1)
                continue

    def _enriquecer(self, ip: str, tipo: str, pps: int) -> Dict:
        """Enriquece datos IP."""
        resultado = {
            'ip': ip,
            'tipo_ataque': tipo,
            'pps': pps,
            'timestamp': datetime.now().isoformat(),
            'pais': 'Desconocido',
            'ciudad': 'Desconocida',
            'asn': 'Desconocido',
            'hostname': 'Desconocido'
        }
        
        # GeoIP City
        if self.city_reader:
            try:
                resp = self.city_reader.city(ip)
                resultado['pais'] = resp.country.name or 'N/A'
                resultado['ciudad'] = resp.city.name or 'N/A'
            except:
                pass
        
        # ASN
        if self.asn_reader:
            try:
                resp = self.asn_reader.asn(ip)
                resultado['asn'] = f"AS{resp.autonomous_system_number} - {resp.autonomous_system_organization}"
            except:
                pass
        
        # Reverse DNS
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            resultado['hostname'] = hostname
        except:
            pass
        
        return resultado

    def agregar(self, ip: str, tipo: str, pps: int) -> None:
        """Agrega a queue (non-blocking)."""
        self.queue.put({'ip': ip, 'tipo': tipo, 'pps': pps})

    def _dump_buffer(self):
        """Guarda buffer a JSONL."""
        try:
            with self.log_file.open('a', encoding='utf-8') as f:
                for evento in self.buffer:
                    f.write(json.dumps(evento, ensure_ascii=False) + '\n')
            self.buffer.clear()
        except Exception as e:
            print(f"Error dump logs: {e}")

    def obtener_recientes(self, n: int = 50) -> List[Dict]:
        """Últimos logs para API. Thread-safe read."""
        if not self.log_file.exists():
            return []
        try:
            with self.lock:  # Sincronizar con writer
                with self.log_file.open('r', encoding='utf-8') as f:
                    lines = deque(f, maxlen=n)
            return [json.loads(line.strip()) for line in lines if line.strip()]
        except:
            return []

# Instancia global lazy
enriquecedor = None

def get_enriquecedor():
    global enriquecedor
    if enriquecedor is None:
        enriquecedor = Enriquecedor()
