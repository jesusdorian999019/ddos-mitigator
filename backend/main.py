#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicación principal FastAPI para DDoS Mitigator.
Production-ready: logging centralizado, graceful shutdown, health checks, Swagger, WebSocket correcto.
"""
import asyncio
import threading
import time
import signal
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from typing import List, Dict, Optional

from backend.logger_config import LoggerConfig
from backend.config import get_config
from backend.captura import capturador
from backend.detector import detector
from backend.mitigacion import get_mitigador
from backend.enriquecimiento import get_enriquecedor

# Setup logging
LoggerConfig.setup()
logger = LoggerConfig.get_logger('backend.main')
config = get_config()


# ============== WebSocket Manager ==============
class ConnectionManager:
    """Gestor de conexiones WebSocket thread-safe."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.lock = threading.RLock()
        self.broadcast_count = 0
    
    async def connect(self, websocket: WebSocket):
        """Acepta conexión."""
        await websocket.accept()
        with self.lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket conectado: {len(self.active_connections)} activas")
    
    def disconnect(self, websocket: WebSocket):
        """Desconecta cliente."""
        with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.debug(f"WebSocket desconectado: {len(self.active_connections)} activas")
    
    async def broadcast(self, data: Dict):
        """Envía datos a todos los clientes."""
        self.broadcast_count += 1
        
        dead_connections = []
        with self.lock:
            connections = self.active_connections.copy()
        
        for connection in connections:
            try:
                await asyncio.wait_for(connection.send_json(data), timeout=0.5)
            except Exception as e:
                logger.debug(f"Error enviando a cliente: {e}")
                dead_connections.append(connection)
        
        # Limpiar conexiones muertas
        for conn in dead_connections:
            self.disconnect(conn)


manager = ConnectionManager()


# ============== Monitor Loop ==============
async def monitor_loop():
    """Loop principal de monitoreo con rate limiting."""
    logger.info("Monitor loop iniciado")
    
    mitigador = get_mitigador()
    enriquecedor = get_enriquecedor() if config.get('enriquecimiento_activo') else None
    
    iteration = 0
    
    while True:
        try:
            iteration += 1
            
            # Detectar anomalías
            alertas = detector.escanear_y_detectar()
            
            # Mitigar automáticamente con rate limiting
            max_bloqueos = config.get('max_bloqueos_ciclo', 20)
            bloqueadas = 0
            for alerta in alertas[:max_bloqueos]:
                ip = alerta['ip']
                if not mitigador.esta_bloqueada(ip):
                    mitigador.agregar_ip(ip, config.get('timeout_bloqueo', 600))
                    bloqueadas += 1
            
            if bloqueadas > 0:
                logger.info(f"Bloqueadas {bloqueadas} IPs ({len(alertas)} pendientes en el ciclo)")
            
            # Limpiar alertas antiguas (cada 10 ciclos)
            if iteration % 10 == 0:
                detector.limpiar_alertas_antiguas()
            
            # Stats para broadcast
            top_ips = capturador.top_ips(10)
            bloqueadas_list = mitigador.listar_bloqueadas()
            
            logs_recientes = []
            if enriquecedor:
                try:
                    logs_recientes = enriquecedor.obtener_recientes(5)
                except Exception as e:
                    logger.debug(f"Error obteniendo logs enriquecidos: {e}")
            
            stats = {
                'timestamp': time.time(),
                'iteration': iteration,
                'top_ips': [
                    {'ip': ip, 'pps': pps, 'proto': proto} 
                    for ip, pps, proto in top_ips
                ],
                'bloqueadas_count': len(bloqueadas_list),
                'alertas': len(alertas),
                'alertas_detalle': alertas[:5],
                'logs_enriquecidos': logs_recientes,
                'max_bloqueos_ciclo': max_bloqueos,
                'captura_stats': capturador.estadisticas(),
                'detector_stats': detector.obtener_estadisticas(),
                'mitigacion_stats': mitigador.estadisticas(),
            }
            
            # Broadcast con rate limiting (máx 1 por segundo si no hay alertas críticas)
            if alertas or iteration % 5 == 0:  # Siempre si hay alertas, cada 10s si no
                await manager.broadcast(stats)
            
            await asyncio.sleep(2)  # 2 segundo entre ciclos
        
        except asyncio.CancelledError:
            logger.info("Monitor loop cancelado")
            raise
        except Exception as e:
            logger.error(f"Error en monitor_loop: {e}", exc_info=True)
            await asyncio.sleep(10)


# ============== Lifecycle ==============
monitor_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown events."""
    global monitor_task
    
    # Startup
    logger.info("=== Iniciando DDoS Mitigator ===")
    try:
        # Capturador en thread
        cap_thread = threading.Thread(target=capturador.iniciar, daemon=True, name="Capturador")
        cap_thread.start()
        logger.info("Thread capturador iniciado")
        
        # Monitor loop
        monitor_task = asyncio.create_task(monitor_loop())
        logger.info("Monitor loop iniciado")
        
    except Exception as e:
        logger.error(f"Error en startup: {e}", exc_info=True)
    
    yield  # Server running
    
    # Shutdown
    logger.info("Iniciando shutdown graceful...")
    try:
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        capturador.detener()
        
        # Flush enriquecimiento
        enriquecedor = get_enriquecedor()
        enriquecedor.detener()
        
        logger.info("Shutdown completado")
    except Exception as e:
        logger.error(f"Error en shutdown: {e}", exc_info=True)


# ============== FastAPI App ==============
start_time = time.time()  # Track uptime

app = FastAPI(
    title="DDoS Mitigator",
    description="Sistema de detección y mitigación automática de ataques DDoS",
    version="2.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir frontend
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"No se pudo montar frontend: {e}")


# ============== Endpoints ==============
@app.get("/")
async def read_root():
    """Sirve página principal."""
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


@app.get("/health")
async def health_check():
    """Health check para monitoring."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "uptime": time.time() - start_time,
        "captura_activa": capturador._running,
        "mitigacion_habilitada": get_mitigador().estadisticas()['mitigacion_habilitada'],
    }


@app.get("/stats")
async def estadisticas():
    """Estadísticas generales del sistema."""
    return {
        'timestamp': time.time(),
        'captura': capturador.estadisticas(),
        'detector': detector.obtener_estadisticas(),
        'mitigacion': get_mitigador().estadisticas(),
        'enriquecimiento': get_enriquecedor().estadisticas() if config.get('enriquecimiento_activo') else None,
        'top_ips': capturador.top_ips(20),
    }


@app.get("/top-ips")
async def top_ips(limit: int = 10):
    """Top IPs por PPS."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit debe estar entre 1 y 100")
    top = capturador.top_ips(limit)
    return {'top_ips': top, 'timestamp': time.time()}


@app.get("/bloqueados")
async def bloqueados():
    """IPs bloqueadas."""
    mitigador = get_mitigador()
    try:
        ips = mitigador.listar_bloqueadas()
        return {'ips': ips, 'count': len(ips)}
    except Exception as e:
        logger.error(f"Error listando bloqueados: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/desbloquear/{ip}")
async def desbloquear_ip(ip: str):
    """Desbloquea IP específica."""
    mitigador = get_mitigador()
    result = mitigador.eliminar_ip(ip)
    if result:
        logger.warning(f"IP desbloqueada manualmente: {ip}")
        return {'status': 'success', 'ip': ip}
    else:
        raise HTTPException(status_code=400, detail=f"No se pudo desbloquear {ip}")


@app.post("/bloquear/{ip}")
async def bloquear_ip(ip: str, timeout: int = 600):
    """Bloquea IP específica."""
    mitigador = get_mitigador()
    result = mitigador.agregar_ip(ip, timeout)
    if result:
        logger.warning(f"IP bloqueada manualmente: {ip}")
        return {'status': 'success', 'ip': ip, 'timeout': timeout}
    else:
        raise HTTPException(status_code=400, detail=f"No se pudo bloquear {ip}")


@app.get("/alertas")
async def alertas():
    """Alertas activas."""
    with detector.lock:
        alertas_list = list(detector.alertas_activas.values())
    return {'alertas': alertas_list, 'count': len(alertas_list)}


@app.get("/logs")
async def logs(limit: int = 50):
    """Logs enriquecidos."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="Limit debe estar entre 1 y 500")
    
    enriquecedor = get_enriquecedor()
    if not config.get('enriquecimiento_activo'):
        raise HTTPException(status_code=400, detail="Enriquecimiento deshabilitado")
    
    logs_list = enriquecedor.obtener_recientes(limit)
    return {'logs': logs_list, 'count': len(logs_list)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para datos realtime."""
    await manager.connect(websocket)
    try:
        while True:
            try:
                # Esperar mensajes de ping del cliente (keep-alive)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                # Echo ping-pong
                await websocket.send_json({"type": "pong", "data": data})
            except asyncio.TimeoutError:
                logger.debug("WebSocket timeout (keep-alive OK)")
                continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in manager.active_connections:
            manager.disconnect(websocket)


# ============== Main ==============
def main():
    """Punto de entrada."""
    host = "0.0.0.0"
    port = config.get('puerto_api', 8000)
    
    logger.info(f"Iniciando servidor en {host}:{port}")
    logger.info(f"Documentación en http://localhost:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
        }
    )


if __name__ == "__main__":
    main()

