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
    try:
        asyncio.create_task(monitor_loop())
    except Exception as e:
        logger.warning(f"Monitor loop setup error: {e}")

@app.get("/")
async def read_root():
    frontend_path = 'frontend/index.html'
    if os.path.exists(frontend_path):
        try:
            with open(frontend_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return HTMLResponse(content=content)
        except Exception as e:
            logger.error(f"Error leyendo frontend: {e}")
            return HTMLResponse(content="Error cargando frontend")
    return HTMLResponse(content="Frontend no encontrado")

# Cachear mitigador
_mitigador_cache = None

def get_mitigador_cached():
    global _mitigador_cache
    if _mitigador_cache is None:
        _mitigador_cache = get_mitigador()
    return _mitigador_cache

@app.get("/estadisticas")
async def estadisticas():
    top = capturador.top_ips()
    return {'top_ips': top, 'timestamp': time.time()}

@app.get("/bloqueados")
async def bloqueados():
    mitigador = get_mitigador_cached()
    try:
        return {'ips': mitigador.listar_bloqueadas()}
    except Exception as e:
        logger.error(f"Error listando bloqueados: {e}")
        return {'ips': [], 'error': str(e)}

@app.get("/alertas")
async def alertas():
    with detector.lock:
        alertas_list = list(detector.alertas_activas.values())
    return {'alertas': alertas_list}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                await manager.broadcast({"type": "ping", "data": data})
            except asyncio.TimeoutError:
                logger.warning("WebSocket timeout")
                break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in manager.active_connections:
            manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

