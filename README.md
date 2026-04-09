# DDoS Mitigator 2.0

Sistema profesional, production-ready de detección y mitigación automática de ataques DoS/DDoS para servidores Linux.

[![Arquitectura](docs/arquitectura.png)](docs/arquitectura.md)

## Características Principales

### Detección
* Captura en tiempo real: Scapy analizando paquetes por IP y protocolo
* Análisis de PPS: Detección de anomalías por IP (TCP SYN, UDP, ICMP)
* Baseline dinámico: Media móvil adaptativa (últimos 60s)
* Umbrales inteligentes: Configurables y adaptativos

### Mitigación
* Bloqueo kernel: ipset + nftables (DROP automático de paquetes)
* Timeout configurable: Desbloqueo automático tras N segundos
* Whitelist: IPs confiables excluidas de bloqueo
* Rate limiting: Máximo N bloqueos por ciclo (evita falsos positivos)
* Persistencia: Recupera bloqueados tras reinicio

### Análisis Forense
* Enriquecimiento GeoIP: País, ciudad, coordenadas
* Datos ASN/ISP: Información del operador
* Reverse DNS: Resolución de nombres de hosts
* Logs JSONL: Persistencia completa de eventos
* Background async: No afecta detección principal

### Panel Web
* WebSocket nativo: Actualización en tiempo real (2s)
* Gráficos interactivos: Chart.js con PPS en vivo
* Métricas dashboard: Alertas, bloqueados, estado sistema
* API REST completa: Endpoints para integración
* Swagger/OpenAPI: Documentación automática en `/docs`

### Production-Ready
* Logging centralizado: Rotación automática de logs (10MB x 5 backups)
* Graceful shutdown: Cierre limpio con flush de datos
* Health checks: Endpoint `/health` para monitoreo
* Thread-safe: Sincronización completa en concurrencia
* Validación robusta: IPs, CIDR, IPv6 soportados
* Error handling: Resiliente a fallos de componentes
* Auto-recovery: Reintentos con backoff exponencial

## Requisitos

| Componente | Mínimo | Recomendado |
|-----------|--------|------------|
| SO | Ubuntu/Debian 20.04+ | Ubuntu 22.04+ |
| Python | 3.9 | 3.11+ |
| RAM | 512MB | 2GB+ |
| CPU | 2 cores | 4+ cores |
| Privilegios | root (captura/mitigación) | root |

## Instalación Rápida

```bash
# Clonar/descargar repo
cd ddos-mitigator

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

## Configuración (config.yaml)

```yaml
# Red
interfaz: eth0                    # Interfaz a monitorear (eth0, ens0, wlan0, etc)
puerto_api: 8000                  # Puerto del API

# Detección
baseline_pps: 100                 # PPS baseline inicial (aprende en 60s)
multiplicador_alerta: 3.0         # Factor de multiplicación para generar alertas
max_alertas_cache: 10000          # Máximo de alertas en memória

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

## Endpoints API

### Estadísticas
```bash
GET /stats                        # Estad general (capturas, alertas, etc)
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
GET /logs                         # Logs enriquecidos (GeoIP, ASN, etc)
GET /health                       # Status del sistema
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
# Health
curl http://localhost:8000/health

# Estadísticas
curl http://localhost:8000/stats

# Bloquear manual
curl -X POST http://localhost:8000/bloquear/192.168.1.100?timeout=300

# Ver bloqueados
curl http://localhost:8000/bloqueados | jq
```

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      Red / Interfaz                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼────┐      ┌─────▼──────┐    ┌─────▼──────┐
    │ Scapy  │      │ nftables   │    │ Estadísticas
    │ Sniff  │      │ +ipset     │    │ y Logs
    │ (PPS)  │      │ (Bloqueo)  │    │
    └───┬────┘      └─────▲──────┘    └─────┬──────┘
        │                 │                  │
        │         [Middleware Centralizado]
        │                 │                  │
    ┌───▼─────────┐    ┌──▼──────────┐   ┌──▼────────────┐
    │  Detector   │───▶│  Mitigador  │   │Enriquecedor   │
    │  (Baseline) │    │  (ipset add)│   │ (GeoIP/ASN)   │
    └─────────────┘    └─────────────┘   └──┬────────────┘
                                             │
                                      ┌──────▼──────┐
                                      │  Backend    │
                                      │  FastAPI    │
                                      │  /stats/api │
                                      │  /ws        │
                                      └──────┬──────┘
                                             │
                                      ┌──────▼──────┐
                                      │   Frontend  │
                                      │  Chart.js   │
                                      │  WebSocket  │
                                      └─────────────┘
```

## Performance

| Métrica | Specs |
|---------|--------|
| PPS máximo | 100k+ (límite interfaz) |
| Latencia bloqueo | < 100ms (kernel) |
| Memory por IP | ~500 bytes (cache) |
| CPU | 5-10% (idle), 20-30% (bajo ataque) |
| WebSocket broadcast | 2s (configurable) |

## Consideraciones de Seguridad

* Requiere privilegios root (captura de paquetes + nftables)
* Ejecutar en entorno controlado/aislado
* Validar whitelist antes de producción
* Usar en servidor dedicado Linux
* Baseline aprende tráfico normal (~5 min)
* Timeout evita bloqueos permanentes
* Monitorear logs para falsos positivos
* Rate limiting previene cascadas
* CORS deshabilitado en producción
* Asegurar acceso físico/SSH único

## Logs

**Ubicación**: logs/ddos_mitigator.log

**Rotación automática**: 10MB x 5 backups

**Niveles**:
* DEBUG: Muy verboso (profiling, detalles)
* INFO: Eventos importantes (bloqueados, cambios)
* WARNING: Problemas no críticos
* ERROR: Errores que requieren atención

**Logs forenses**:
* data/logs.jsonl: Eventos enriquecidos (GeoIP, ASN, RDNS)
* Una línea por evento = fácil parsear

## Troubleshooting

### "ipset no existe"
```bash
sudo ./scripts/setup.sh  # Recrear tablas
```

### "Permission denied - Scapy sniff"
```bash
sudo venv/bin/uvicorn backend.main:app  # Ejecutar con root
```

### Alto consumo de RAM
```yaml
# Reducir en config.yaml
max_alertas_cache: 5000
cache_enriquecimiento: 1000
```

### WebSocket no se conecta
* Revisar CORS en main.py
* Verificar firewall (puerto 8000)
* Inspeccionar con DevTools Web

## Production Deployment

### Docker (recomendado)
```bash
# Construir imagen
docker build -t ddos-mitigator .

# Ejecutar
docker run --privileged --net=host \
  -v /path/to/config.yaml:/app/config.yaml \
  -p 8000:8000 \
  ddos-mitigator
```

### Systemd Service
```ini
[Unit]
Description=DDoS Mitigator
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ddos-mitigator
ExecStart=/opt/ddos-mitigator/venv/bin/uvicorn backend.main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Documentación Técnica

Ver [docs/arquitectura.md](docs/arquitectura.md) para detalles profundos.

## Licencia

GPL-3.0 - Código abierto para uso educativo/comercial

## Autor

Sistema desarrollado para detección automatizada de ataques DDoS.

---

Versión: 2.0 | Última actualización: 2024 | Estatus: Production-Ready

## 📋 Requisitos

| Componente | Mínimo | Recomendado |
|-----------|--------|------------|
| SO | Ubuntu/Debian 20.04+ | Ubuntu 22.04+ |
| Python | 3.9 | 3.11+ |
| RAM | 512MB | 2GB+ |
| CPU | 2 cores | 4+ cores |
| Privilegios | root (captura/mitigación) | root |

## ⚡ Instalación Rápida

```bash
# Clonar/descargar repo
cd ddos-mitigator

# Ejecutar setup.sh (instala deps, crea venv, prepara ipset/nftables)
sudo ./scripts/setup.sh

# Editar configuración
nano config.yaml

# Activar venv
source venv/bin/activate

# Ejecutar (con root para captura)
sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Abrir en navegador: **http://localhost:8000**

## ⚙️ Configuración (config.yaml)

```yaml
# Red
interfaz: eth0                    # Interfaz a monitorear (eth0, ens0, wlan0, etc)
puerto_api: 8000                  # Puerto del API

# Detección
baseline_pps: 100                 # PPS baseline inicial (aprende en 60s)
multiplicador_alerta: 3.0         # Factor de multiplicación para generar alertas
max_alertas_cache: 10000          # Máximo de alertas en memória

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
workers_enriquecimiento: 2        # Threads workers para éste

# Sistema
log_level: INFO                   # DEBUG, INFO, WARNING, ERROR
log_dir: logs                     # Directorio de logs
data_path: data                   # Ruta de datos (GeoIP, SQLite, etc)
modo_desarrollo: false            # DEBUG mode
```

## 📊 Endpoints API

### Estadísticas
```bash
GET /stats                        # Estad general (capturas, alertas, etc)
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
GET /health                       # Status del sistema
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

## 🧪 Pruebas y Simulación

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
# Health
curl http://localhost:8000/health

# Estadísticas
curl http://localhost:8000/stats

# Bloquear manual
curl -X POST http://localhost:8000/bloquear/192.168.1.100?timeout=300

# Ver bloqueados
curl http://localhost:8000/bloqueados | jq
```

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      Red / Interfaz                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
    ┌───▼────┐      ┌─────▼──────┐    ┌─────▼──────┐
    │ Scapy  │      │ nftables   │    │ Estadísticas
    │ Sniff  │      │ +ipset     │    │ y Logs
    │ (PPS)  │      │ (Bloqueo)  │    │
    └───┬────┘      └─────▲──────┘    └─────┬──────┘
        │                 │                  │
        │         [Thread-safe ComsMiddleware]
        │                 │                  │
    ┌───▼─────────┐    ┌──▼──────────┐   ┌──▼────────────┐
    │  Detector   │───▶│  Mitigador  │   │Enriquecedor   │
    │  (Baseline) │    │  (ipset add)│   │ (GeoIP/ASN)   │
    └─────────────┘    └─────────────┘   └──┬────────────┘
                                             │
                                      ┌──────▼──────┐
                                      │  Backend    │
                                      │  FastAPI    │
                                      │  /stats/api │
                                      │  /ws        │
                                      └──────┬──────┘
                                             │
                                      ┌──────▼──────┐
                                      │   Frontend  │
                                      │  Chart.js   │
                                      │  WebSocket  │
                                      └─────────────┘
```

## 📈 Performance

| Métrica | Specs |
|---------|--------|
| PPS máximo | 100k+ (límite interfaz) |
| Latencia bloqueo | < 100ms (kernel) |
| Memory por IP | ~500 bytes (cache) |
| CPU | ~5-10% (idle), 20-30% (bajo ataque) |
| WebSocket broadcast | 2s (configurable) |

## 🔒 Consideraciones de Seguridad

⚠️ **Crítico**: 
- Requiere **privilegios root** (captura de paquetes + nftables)
- Ejecutar en entorno controlado/aislado
- Validar whitelist antes de producción

✅ **Recomendaciones**:
- Usar en servidor dedicado Linux
- Baseline aprende tráfico normal (~5 min)
- Timeout evita bloqueos permanentes
- Monitorear logs para falsos positivos
- Rate limiting previene cascadas
- CORS deshabilitado en producción
- Asegurar acceso físico/SSH único

## 📝 Logs

**Ubicación**: `logs/ddos_mitigator.log`

**Rotación automática**: 10MB × 5 backups

**Niveles**:
- `DEBUG`: Muy verboso (profiling, detalles)
- `INFO`: Eventos importantes (bloqueados, cambios)
- `WARNING`: Problemas no críticos
- `ERROR`: Errores que requieren atención

**Logs forenses**:
- `data/logs.jsonl`: Eventos enriquecidos (GeoIP, ASN, RDNS)
- Una línea por evento = fácil parsear

## 🆘 Troubleshooting

### "ipset no existe"
```bash
sudo ./scripts/setup.sh  # Recrear tablas
```

### "Permission denied - Scapy sniff"
```bash
sudo venv/bin/uvicorn backend.main:app  # Ejecutar con root
```

### Alto consumo de RAM
```yaml
# Reducir en config.yaml
max_alertas_cache: 5000
cache_enriquecimiento: 1000
```

### WebSocket no se conecta
- Revisar CORS en `main.py`
- Verificar firewall (puerto 8000)
- Inspeccionar con DevTools Web

## 🚀 Production Deployment

### Docker (recomendado)
```bash
# Construir imagen
docker build -t ddos-mitigator .

# Ejecutar
docker run --privileged --net=host \
  -v /path/to/config.yaml:/app/config.yaml \
  -p 8000:8000 \
  ddos-mitigator
```

### Systemd Service
```ini
[Unit]
Description=DDoS Mitigator
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ddos-mitigator
ExecStart=/opt/ddos-mitigator/venv/bin/uvicorn backend.main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 📚 Documentación Técnica

Ver [docs/arquitectura.md](docs/arquitectura.md) para detalles profundos.

## 📄 Licencia

GPL-3.0 - Código abierto para uso educativo/comercial

## 👤 Autor

Sistema desarrollado para detección automatizada de ataques DDoS.

---

**Versión**: 2.0 | **Última actualización**: 2024 | **Estatus**: Production-Ready ✅
* Solo defensivo (no ofensivo)

## Limitaciones

* Un solo interfaz (configurable)
* Detección estadística (posibles falsos ±)
* No Layer7 (solo L3/L4)
* Linux-only (nftables/ipset)

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| "Permission denied" | `sudo` |
| No captura paquetes | Verificar interfaz `ip link` |
| ipset no existe | `./scripts/setup.sh` |
| Panel vacío | Verificar WebSocket `localhost:8000/ws` |

## Mejoras Futuras

* Multi-interfaz
* Machine Learning anomalías
* GeoIP bloqueo
* Integración Fail2Ban
* Alertas Slack/Discord
* Dashboard histórico (SQLite)

## Licencia

MIT License - Uso libre con atribución.


---
**Desarrollado para producción con estándares empresariales por jesusdorian999019**

