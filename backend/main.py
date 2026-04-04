#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicación principal FastAPI para DDoS Mitigator.
Integra captura, detección, mitigación y panel realtime.
"""
import asyncio
import threading
import time
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
from typing import List, Dict
from backend.config import config
from backend.captura import capturador
from backend.detector import detector
from backend.mitigacion import get_mitigador
try:
    from backend.enriquecimiento import get_enriquecedor
except ImportError:
    get_enriquecedor = None

logging.basicConfig(level=config.get('log_level', 'INFO'), 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="DDoS Mitigator", version="1.0")

# Gestión de conexiones WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: Dict):
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(data)
            except:
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Background task para monitoreo
async def monitor_loop():
    """Loop principal de monitoreo con rate limiting y enriquecimiento."""
    mitigador = get_mitigador()  # Auto-carga bloqueados persistidos
    enriquecedor = get_enriquecedor() if config.get('enriquecimiento_activo', True) else None
    
    while True:
        try:
            # Detectar anomalías (incluye enriquecimiento background)
            alertas = detector.escanear_y_detectar()
            
            # Mitigar automáticamente (rate limited)
            max_bloqueos = config.get('max_bloqueos_ciclo', 20)
            for alerta in alertas[:max_bloqueos]:
                ip = alerta['ip']
                if not mitigador.esta_bloqueada(ip):
                    mitigador.agregar_ip(ip, config.get('timeout_bloqueo', 600))
                    logger.info(f"Bloqueo prioritario: {ip} [{len(alertas)} pendientes]")
            
            # Stats para broadcast
            top_ips = capturador.top_ips(10)
            bloqueadas = mitigador.listar_bloqueadas()
            logs_recientes = []
            if enriquecedor:
                try:
                    logs_recientes = enriquecedor.obtener_recientes(5)
                except Exception:
                    pass
            
            stats = {
                'timestamp': time.time(),
                'top_ips': [{'ip': ip, 'pps': pps, 'proto': proto} for ip, pps, proto in top_ips],
                'bloqueadas_count': len(bloqueadas),
                'alertas': len(alertas),
                'alertas_detalle': alertas[:5],
                'logs_enriquecidos': logs_recientes,
                'max_bloqueos_ciclo': max_bloqueos
            }
            await manager.broadcast(stats)
            
            await asyncio.sleep(2)  # Reactivo
            
        except Exception as e:
            logger.error(f"Error en monitor_loop: {e}")
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup():
    logger.info("Iniciando DDoS Mitigator - Mitigación reactiva local")
    threading.Thread(target=capturador.iniciar, daemon=True).start()
    asyncio.create_task(monitor_loop())

@app.get("/")
async def read_root():
    return HTMLResponse(content=open('frontend/index.html').read() if os.path.exists('frontend/index.html') else "Frontend pendiente")

@app.get("/estadisticas")
async def estadisticas():
    top = capturador.top_ips()
    return {'top_ips': top, 'timestamp': time.time()}

@app.get("/bloqueados")
async def bloqueados():
    mitigador = get_mitigador()
    return {'ips': mitigador.listar_bloqueadas()}

@app.get("/alertas")
async def alertas():
    return {'alertas': list(detector.alertas_activas.values())}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast({"type": "ping", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

