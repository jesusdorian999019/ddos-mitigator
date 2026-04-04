# Arquitectura del Sistema DDoS Mitigator

## Diagrama de Alto Nivel

```
[Red] --> [nftables + ipset] --> [Servidor Linux]
             ↑
       [Scapy Sniff] --> [Detector] --> [Mitigador] 
             |                  | 
        WebSocket realtime    [Enriquecedor*] --> data/logs.jsonl
             ↓                       (GeoIP/ASN/RDNS)
       [FastAPI API] <-- [Frontend Panel]
```

*Background threads, non-blocking

## Componentes Principales

### 1. Captura (captura.py)
- Scapy threaded sniff en interfaz configurable
- Contadores PPS atómicos por IP+protocolo
- Ventana móvil 5s
- Filtrado paquetes legítimos (SSH/HTTP)

### 2. Detección (detector.py)
- Baseline dinámico por IP (media móvil 60s)
- Umbral adaptativo: baseline × multiplicador (default 3.0)
- Clasificación: SYN/UDP/ICMP Flood

### 3. Mitigación (mitigacion.py)
- ipset `ddos_blacklist` con timeout
- nftables ruleset `ddos_filter` (input/forward DROP)
- Whitelist configurable
- Validación root/sets existentes

### 4. API y Panel (main.py + frontend)
```
Endpoints:
GET /estadisticas     # Top IPs PPS
GET /bloqueados       # Lista bloqueadas  
GET /alertas         # Alertas recientes
WS  /ws              # Realtime stats
```

### Flujo de Ejecución
```
1. setup.sh → ipset + nftables
2. main.py → scapy sniff + loop detección 5s
3. Detecta → ipset add → nftables DROP
4. WebSocket → Panel Chart.js realtime
```

## Rendimiento
- O(1) lookups ipset (hash table)
- Thread-safe counters
- No bottleneck Python (kernel filtra)
- Escalable a 10k+ PPS
