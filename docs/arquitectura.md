# Arquitectura Técnica - DDoS Mitigator 2.0

## Visión General

Sistema de detección y mitigación multi-capa para ataques DoS/DDoS:
1. **Capa de Kernel**: nftables + ipset (DROP en kernel)
2. **Capa de Detección**: Scapy + análisis estadístico
3. **Capa de Aplicación**: FastAPI con WebSocket realtime
4. **Capa de Enriquecimiento**: GeoIP, ASN, Reverse DNS (async)

```
    ┌─────────────────────────────────────────────────┐
    │          Red / Interfaz de Red                  │
    └────────────────┬────────────────────────────────┘
                     │ Tráfico IP
         ┌───────────┴──────────┐
         │                      │
    ┌────▼────┐            ┌────▼─────────┐
    │ Legítimo│            │ DDoS Attack  │
    │  (PASS) │            │ (DETECT)     │
    └────┬────┘            └────┬─────────┘
         │                      │
         │                  ┌───▼────────────────┐
         └─────────┬────────►│① SCAPY CAPTURE    │
                  │         │ - Thread-safe      │
                  │         │ - PPS por IP       │
                  │         │ - Ventana móvil 5s │
                  │         └───┬────────────────┘
                  │             │
                  │         ┌───▼──────────────────┐
                  │         │② DETECTOR           │
                  │         │ - Baseline dinámico  │
                  │         │ - Anomaly detection  │
                  │         │ - Clasificación     │
                  │         └───┬──────────────────┘
                  │             │ Alertas
         ┌────────┴─────────────┬──────────────────┐
         │                      │                  │
    ┌────▼────┐           ┌────▼──────┐      ┌───▼──────────┐
    │nftables  │           │ Mitigador │      │Enriquecedor  │
    │ +ipset   │           │ ipset add │      │(GeoIP/ASN)   │
    │(kernel)  │           │ + timeout │      │Async workers │
    └────▲────┘           └────┬──────┘      └───┬──────────┘
         │                      │                  │
         │ DROP packets     ┌───▼──────────────────▼─┐
         └──────────────────│   Data Persistence    │
                            │ - Logs JSONL          │
                            │ - Bloqueados JSON     │
                            │ - Cache LRU           │
                            └───────────────────────┘
                                   │
                            ┌──────▼───────┐
                            │② RESTful API │
                            │   FastAPI    │
                            │   /stats     │
                            │   /bloqueados│
                            │   /ws        │
                            │   /docs      │
                            └──────┬───────┘
                                   │
                            ┌──────▼──────────┐
                            │④ Frontend Panel│
                            │ HTML/CSS/JS    │
                            │ WebSocket      │
                            │ Chart.js       │
                            └────────────────┘
```

## Componentes Detallados

### 1. Captura (captura.py)

**Responsabilidad**: Capturar paquetes IP y calcular PPS por IP

**Arquitectura**:
```python
Capturador
├── Thread sniffing (Scapy)
│   └── packet_handler() - O(1) append
├── contadores{proto_key: deque[timestamps]}
│   └── Ventana móvil 5 segundos
├── top_ips(n) - Retorna top N
└── Estadísticas (paquetes captados, etc)
```

**Características**:
- Thread-safe con `RLock`
- Memory leak prevention (límite 100k contadores)
- Limpieza de timestamps outdated
- Filtro de paquetes (no SSH/HTTPS)
- O(1) inserción, O(N) top_ips

**Métodos críticos**:
```python
contar_paquete(pkt)      # Handler de Scapy
pps_por_ip(ip)           # PPS instantáneo
top_ips(n)               # Top N IPs
limpiar()                # Flush counters
detener()                # Graceful stop
```

### 2. Detector (detector.py)

**Responsabilidad**: Detectar anomalías basado en umbrales dinámicos

**Algoritmo de Detección**:
```
Para cada IP en top 20:
  baseline (t) = media(PPS últimos 60s)
  umbral = baseline(t) * multiplicador
  
  Si PPS > umbral:
    → ALERTA (enviar a enriquecer)
    → Almacenar en alertas_activas
```

**Features**:
- Baseline móvil con deque maxlen=12 (60s)
- Anti-spam con LRU cache (evita re-enrique)
- Clasificación de ataque (SYN/UDP/ICMP)
- Limpieza de alertas antiguas (5 min)
- Stats de detección (total, anomalías)

**Thread Safety**:
- Lock en actualizar_baseline
- Cache LRU thread-safe
- con context managers

### 3. Mitigador (mitigacion.py)

**Responsabilidad**: Bloquear IPs mediante ipset + nftables

**Flow**:
```
agregar_ip(ip, timeout)
├── Validar IP (regex + library)
├── Check whitelist
├── Check ya bloqueada (cache)
├── cmd: ipset add ddos_blacklist ip [timeout N]
├── Guardar a JSON (persistencia)
└── Return True/False
```

**Persistencia**:
- bloqueados.json: timestamp + lista IPs
- Atomic write (temp → rename)
- Carga al startup

**Seguridad**:
- IPv4 + IPv6 + CIDR validados
- Shell-safe (no inyección)
- Retry automático (3 intentos)
- Whitelist inmune

### 4. Enriquecedor (enriquecimiento.py)

**Responsabilidad**: Enriquecer IPs en background (no bloquea detección)

**Arquitectura Async**:
```
Main Thread           Worker Threads (2x)
agregar() →──────┐
                 │ Queue(max_size=10k)
                 └→ _worker_loop()
                    ├── Dequeue IP
                    ├── GeoIP Lookup
                    ├── ASN Lookup
                    ├── DNS Reverso
                    ├── Componer JSON
                    └── Buffer.append()
                        └── Flush a JSONL
```

**Features**:
- Workers configurables (default 2)
- Queue con límite (evita OOM)
- Buffer auto-flush (100 eventos)
- Timeouts en operaciones de socket
- Fallback si GeoIP DBs ausentes

**Datos Enriquecidos**:
```json
{
  "ip": "203.0.113.1",
  "tipo_ataque": "SYN Flood",
  "pps": 5000,
  "timestamp": "2024-01-15T10:23:45.123Z",
  "pais": "China",
  "ciudad": "Beijing",
  "asn": "AS4134 Chinanet",
  "hostname": "example.com"
}
```

### 5. API (main.py)

**Framework**: FastAPI (Async + ASGI)

**Endpoints**:
```
GET  /                    Sirve index.html
GET  /health              Status del sistema
GET  /stats               Métricas globales
GET  /top-ips?limit=10    Top IPs por PPS
GET  /bloqueados          Lista bloqueadas
POST /bloquear/{ip}       Bloqueo manual
POST /desbloquear/{ip}    Desbloqueo manual
GET  /alertas             Alertas activas
GET  /logs                Logs enriquecidos
GET  /docs                Swagger UI
WS   /ws                  WebSocket realtime
```

**Lifecycle**:
```
startup:
  ├── Capturador.iniciar() → Thread
  ├── monitor_loop() → Task Async
  └── ConnectionManager ready

running:
  └── monitor_loop() cada 2s
      ├── detector.escanear_y_detectar()
      ├── mitigador.agregar_ip() (max 20/ciclo)
      ├── manager.broadcast(stats) → WS
      └── Limpiar alertas antiguas

shutdown:
  ├── Cancelar monitor_loop
  ├── capturador.detener()
  ├── enriquecedor.detener()
  └── Flush de logs
```

## Performance

### Escalabilidad

| Métrica | Capacidad |
|---------|-----------|
| PPS máximo | 100k+ (límite interfaz) |
| IPs simultáneas | 1000-5000 |
| Alertas en cache | 10k |
| WebSocket connections | 100-1000 |
| Memory (baseline) | ~100MB |
| Memory (pico) | ~500MB |

### Latencies

| Operación | Latencia |
|-----------|----------|
| Captura → Detección | 0-5ms |
| Detección → Bloqueo | 50-100ms |
| Bloqueo kernel | <1ms |
| WebSocket broadcast | 100-500ms |

### Bottlenecks

1. **CPU-bound**: Cálculo PPS (mitigado con O(1) lookups)
2. **I/O-bound**: DNS reverso (async worker)
3. **Memory**: Contadores sin límite (mitigado con eviction)

## Thread Safety

### Sincronización

| Componente | Estrategia | Lock Type |
|-----------|-----------|-----------|
| Capturador | contadores | RLock |
| Detector | alertas_activas | RLock |
| Mitigador | bloqueadas | RLock |
| Enriquecedor | buffer | Lock |
| ConnectionManager | active_connections | Lock |

### Race Conditions Prevenidas

- ✅ Doble inicio de captura
- ✅ Concurrent bloqueados/desbloqueados
- ✅ Buffer flush durante enriquecimiento
- ✅ WebSocket broadcast durante update

## Tolerancia a Fallos

### Resiliencia

```
Captura fails     → Logger warn + retry
Detección fails   → Skip ciclo, continuar
Bloqueo falla     → Retry 3x con backoff
DNS timeout       → Fallback a "Unknown"
GeoIP DB missing  → Continuar sin GeoIP
WebSocket drops   → Auto-reconexión cliente
API overload      → Rate limit automático
```

### Data Durability

- Bloqueados: Persist JSON
- Logs: Append-only JSONL (atomístico)
- Config: Validación en load

## Security Considerations

⚠️ **Root Required**: Captura + nftables

✅ **Mitigaciones**:
- Validación IP robusta (regex + library)
- Whitelist configurable
- Rate limit de bloqueos
- Timeout auto-desbloqueo
- Audit log completo
- No almacena password/secrets

## Escalabilidad Horizontal (Futuro)

Arquitectura actual es **single-node**. Para cluster:

```
┌─────────────────┐
│  Load Balancer  │
└────────┬────────┘
    │    │    │
┌───▼┐ ┌─▼──┐ ┌──▼──┐
│    │ │    │ │     │  Mitigadores
│ M1 │-│ M2 │-│ M3  │  (redundancia)
└─┬──┘ └─┬──┘ └──┬──┘
  │      │       │
  └──────┼───────┘
        │
    ┌───▼────────┐
    │ Redis Sync │ Compartir estado
    │ (alertas)  │
    └────────────┘
```

Cambios requeridos:
- Persistencia con SQLite/PostgreSQL
- SyncEvent entre nodos (Redis/etcd)
- Dedicated Detector node
- Distributed logging

## Monitoreo y Observabilidad

### Métricas Exportadas

```python
captura_stats = {
  'paquetes_capturados': int,
  'ips_unicas': int,
  'ultimo_paquete': timestamp
}

detector_stats = {
  'alertas_totales': int,
  'anomalias_detectadas': int,
}

mitigacion_stats = {
  'ips_bloqueadas': int,
  'max_bloqueables': int,
  'mitigacion_habilitada': bool
}
```

### Health Checks

```bash
curl http://localhost:8000/health
{
  "status": "healthy",
  "captura_activa": true,
  "mitigacion_habilitada": true,
  "timestamp": 1704015824.123
}
```

---

**Última actualización**: 2024
**Versión Arquitectura**: 2.0
**Status**: Production-Ready

