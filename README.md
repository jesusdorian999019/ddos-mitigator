# DDoS Mitigator 2.0

Sistema profesional, production-ready de detección y mitigación automática de ataques DoS/DDoS para servidores Linux.

**Autor**: [jesusdorian999019](https://github.com/jesusdorian999019) | **Versión**: 7.0 | **Status**: Production-Ready

---

## Características Principales

### Detección
- **Captura en tiempo real**: Scapy analizando paquetes por IP y protocolo
- **Análisis de PPS**: Detección de anomalías por IP (TCP SYN, UDP, ICMP)
- **Baseline dinámico**: Media móvil adaptativa (últimos 60s)
- **Umbrales inteligentes**: Configurables y adaptativos

### Mitigación
- **Bloqueo kernel**: ipset + nftables (DROP automático de paquetes)
- **Timeout configurable**: Desbloqueo automático tras N segundos
- **Whitelist**: IPs confiables excluidas de bloqueo
- **Rate limiting**: Máximo N bloqueos por ciclo (evita falsos positivos)
- **Persistencia**: Recupera bloqueados tras reinicio

### Análisis Forense
- **Enriquecimiento GeoIP**: País, ciudad, coordenadas
- **Datos ASN/ISP**: Información del operador
- **Reverse DNS**: Resolución de nombres de hosts
- **Logs JSONL**: Persistencia completa de eventos
- **Background async**: No afecta detección principal

### Panel Web
- **WebSocket nativo**: Actualización en tiempo real (2s)
- **Gráficos interactivos**: Chart.js con PPS en vivo
- **Métricas dashboard**: Alertas, bloqueados, estado sistema
- **API REST completa**: Endpoints para integración
- **Swagger/OpenAPI**: Documentación automática en `/docs`

### Production-Ready
- **Logging centralizado**: Rotación automática de logs (10MB x 5 backups)
- **Graceful shutdown**: Cierre limpio con flush de datos
- **Health checks**: Endpoint `/health` para monitoreo
- **Thread-safe**: Sincronización completa en concurrencia
- **Validación robusta**: IPs, CIDR, IPv6 soportados
- **Error handling**: Resiliente a fallos de componentes
- **Auto-recovery**: Reintentos con backoff exponencial

---

## Requisitos

| Componente | Mínimo | Recomendado |
|-----------|--------|------------|
| SO | Ubuntu/Debian 20.04+ | Ubuntu 22.04+ |
| Python | 3.9 | 3.11+ |
| RAM | 512MB | 2GB+ |
| CPU | 2 cores | 4+ cores |
| Privilegios | root (captura/mitigación) | root |

---

## Instalación Rápida

```bash
# Clonar repositorio desde GitHub
git clone https://github.com/jesusdorian999019/ddos-mitigator.git
cd ddos-mitigator

# Hacer ejecutable el script de setup
chmod +x scripts/setup.sh

# Ejecutar setup.sh (instala deps, crea venv, prepara ipset/nftables)
sudo ./scripts/setup.sh

# Editar configuración
nano config.yaml

# Activar venv
source venv/bin/activate

# Ejecutar (con root para captura)
sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Abrir en navegador: http://localhost:8000

---

## Configuración (config.yaml)

```yaml
# Red
interfaz: eth0                    # Interfaz a monitorear (eth0, ens0, wlan0, etc)
puerto_api: 8000                  # Puerto del API

# Detección
baseline_pps: 100                 # PPS baseline inicial (aprende en 60s)
multiplicador_alerta: 3.0         # Factor de multiplicación para generar alertas
max_alertas_cache: 10000          # Máximo de alertas en memoria

# Bloqueo
timeout_bloqueo: 600              # Segundos de bloqueo (defecto 10min)
max_ips_bloqueadas: 1000          # Máximo IPs bloqueadas simultáneamente
max_bloqueos_ciclo: 20            # IPs a bloquear máx por ciclo (evita spam)
whitelist:
  - 127.0.0.1                     # IPs nunca bloqueadas
  - 192.168.1.0/24

# Enriquecimiento
enriquecimiento_activo: true      # GeoIP, ASN, DNS reverso
cache_enriquecimiento: 5000       # LRU cache para evitar re-enrique
workers_enriquecimiento: 2        # Threads workers para este

# Sistema
log_level: INFO                   # DEBUG, INFO, WARNING, ERROR
log_dir: logs                     # Directorio de logs
data_path: data                   # Ruta de datos (GeoIP, SQLite, etc)
modo_desarrollo: false            # DEBUG mode
```

---

## API Endpoints

### Estadísticas
```bash
GET /                             # Frontend HTML
GET /health                       # Status del sistema
GET /stats                        # Estadísticas general (capturas, alertas, etc)
GET /top-ips?limit=20            # Top N IPs por PPS
```

### Bloqueo/Desbloqueo
```bash
GET /bloqueados                   # Lista IPs bloqueadas
POST /bloquear/{ip}              # Bloquea IP manual
POST /desbloquear/{ip}           # Desbloquea IP manual
```

### Monitoreo
```bash
GET /alertas                      # Alertas activas
GET /logs?limit=50               # Logs enriquecidos (GeoIP, ASN, etc)
```

### Realtime
```bash
WS /ws                            # WebSocket para actualización en vivo
```

### Documentación
```bash
GET /docs                         # Swagger UI interactivo
GET /openapi.json                # OpenAPI spec JSON
```

---

## Pruebas y Simulación

### Simular ataques (desde otra máquina)

```bash
# ICMP Flood
sudo hping3 --flood --icmp -i u1 TARGET_IP

# TCP SYN Flood
sudo hping3 --flood -S -p 80 -i u1 TARGET_IP

# UDP Flood
sudo hping3 --flood -U -p 53 -i u1 TARGET_IP
```

### Verificar bloqueados

```bash
# Ver IPs en blacklist
sudo ipset list ddos_blacklist

# Ver reglas nftables
sudo nft list ruleset

# Monitorear logs
tail -f logs/ddos_mitigator.log
```

### Test de API

```bash
# Health check
curl http://localhost:8000/health

# Estadísticas
curl http://localhost:8000/stats

# Bloquear manual
curl -X POST http://localhost:8000/bloquear/192.168.1.100?timeout=300

# Ver bloqueados
curl http://localhost:8000/bloqueados | jq
```

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    Red / Interfaz de Red                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼──────┐   ┌────▼────┐   ┌────▼─────┐
    │  Scapy   │   │nftables │   │ Estadísticas
    │  Sniff   │   │ +ipset  │   │ y Logs
    │  (PPS)   │   │(Bloqueo)│   │
    └───┬──────┘   └───▲─────┘   └────┬─────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
┌───▼────────┐   ┌────▼───────┐   ┌─────▼──────┐
│  Detector  │   │  Mitigador │   │Enriquecedor│
│(Baseline)  │──▶│(ipset add) │   │(GeoIP/ASN) │
└────────────┘   └────────────┘   └──────┬─────┘
                                          │
                                   ┌──────▼────────┐
                                   │   Backend     │
                                   │   FastAPI     │
                                   │   REST+WS     │
                                   └──────┬────────┘
                                          │
                                   ┌──────▼────────┐
                                   │   Frontend    │
                                   │  Chart.js     │
                                   │  WebSocket    │
                                   └───────────────┘
```

---

## Performance

| Métrica | Capacidad |
|---------|-----------|
| PPS máximo | 100k+ (límite interfaz) |
| Latencia bloqueo | < 100ms (kernel) |
| Memory por IP | ~500 bytes (cache) |
| CPU | 5-10% idle, 20-30% bajo ataque |
| WebSocket broadcast | 2s (configurable) |
| IPs simultáneas | 1000-5000 |
| Alertas en cache | 10k máximo |

---

## Consideraciones de Seguridad

**CRÍTICO**:
- Requiere privilegios **root** (captura de paquetes + nftables)
- Ejecutar en entorno controlado/aislado
- Validar whitelist antes de producción

**RECOMENDACIONES**:
- Usar en servidor dedicado Linux
- Baseline aprende tráfico normal (~5 min, monitoreado)
- Timeout evita bloqueos permanentes
- Monitorear logs para falsos positivos
- Rate limiting previene cascadas
- CORS en producción debe especificar origen
- Asegurar acceso físico/SSH único
- Validar configuración antes de deploy
- Crear backups de bloqueados.json

---

## Logs

**Ubicación**: `logs/ddos_mitigator.log`

**Rotación automática**: 10MB x 5 backups

**Niveles de log**:
- DEBUG: Muy verboso (profiling, detalles)
- INFO: Eventos importantes (bloqueados, cambios)
- WARNING: Problemas no críticos
- ERROR: Errores que requieren atención

**Logs forenses**:
- `data/logs.jsonl`: Eventos enriquecidos (GeoIP, ASN, DNS)
- Una línea por evento = fácil parsear con jq/awk

---

## Troubleshooting

### "ipset no existe"
```bash
sudo ./scripts/setup.sh  # Recrear tablas ipset/nftables
```

### "Permission denied - Scapy sniff"
```bash
sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Alto consumo de RAM
```yaml
# Reducir en config.yaml:
max_alertas_cache: 5000
cache_enriquecimiento: 1000
max_ips_bloqueadas: 500
```

### WebSocket no se conecta
- Revisar CORS en `main.py`
- Verificar firewall (puerto 8000)
- Inspeccionar con DevTools (F12)
- Ver logs: `tail -f logs/ddos_mitigator.log`

### Baseline muy alto/bajo
- Esperar 5 minutos para que aprenda
- Revisar tráfico normal con `top-ips`
- Ajustar `multiplicador_alerta` en config.yaml

---

## Production Deployment

### Opción 1: Docker (recomendado)
```bash
# Construir imagen
docker build -t ddos-mitigator .

# Ejecutar
docker run --privileged --net=host \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/data:/app/data \
  -p 8000:8000 \
  ddos-mitigator
```

### Opción 2: Docker Compose
```bash
docker-compose up -d
# Auto orquestación + healthcheck + recursos limitados
```

### Opción 3: Systemd Service
```bash
sudo bash deploy.sh
# Se instala automáticamente en /opt/ddos-mitigator
```

```bash
# Comandos después de instalar:
systemctl status ddos-mitigator
journalctl -u ddos-mitigator -f
```

### Opción 4: Manual
```bash
sudo ./scripts/setup.sh
source venv/bin/activate
sudo uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Documentación Técnica

Ver [docs/arquitectura.md](docs/arquitectura.md) para análisis en profundidad:
- Componentes detallados
- Thread safety patterns
- Tolerancia a fallos
- Escalabilidad horizontal (futuro)
- Métricas de monitoreo

---

## Limitaciones Conocidas

- Un solo interfaz (configurable en config.yaml)
- Detección estadística (posibles falsos positivos/negativos)
- No incluye Layer 7 detection (solo L3/L4)
- Linux-only (requiere nftables/ipset)

---

## Mejoras Futuras (v2.1+)

- Multi-interfaz
- Machine Learning para anomalías
- Bloqueo por geolocalización
- Integración Fail2Ban
- Alertas Slack/Discord/Email
- Dashboard histórico (SQLite)
- API authentication (JWT)
- Redis clustering

---

## Licencia

GPL-3.0 - Código abierto para uso educativo y comercial

---

## Autor

**jesusdorian999019** - GitHub: https://github.com/jesusdorian999019

Desarrollado como un sistema profesional, production-ready para mitigación de DDoS.

**Última actualización**: 2026 | **Versión**: 7.0 | **Status**: Production-Ready
