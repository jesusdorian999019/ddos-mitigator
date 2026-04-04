# DDoS Mitigator

Sistema profesional de detección y mitigación automática de ataques DoS/DDoS para servidores Linux.

[![Arquitectura](docs/arquitectura.png)](docs/arquitectura.md)

## Características Principales

* **Captura en tiempo real**: Scapy analizando PPS por IP y protocolo (TCP SYN, UDP, ICMP)
* **Detección inteligente**: Umbrales dinámicos (baseline móvil × multiplicador configurable)
* **Mitigación kernel**: ipset + nftables (DROP automático con timeout)
* **Enriquecimiento forense**: GeoIP país/ciudad, ASN/ISP, Reverse DNS (background)
* **Persistencia logs**: data/logs.jsonl con datos completos ataques
* **Panel web realtime**: WebSocket + Chart.js (tráfico, alertas enriquecidas, bloqueados)
* **Alto rendimiento**: Operaciones O(1), thread-safe. **Reactiva heurística** (no 0 falsos positivos)

## Requisitos

* Ubuntu/Debian 20.04+
* Python 3.11+
* Privilegios root para captura/mitigación

## Instalación

```bash
cd ddos-mitigator
sudo ./scripts/setup.sh
# Edita config.yaml según tu entorno
source venv/bin/activate
sudo uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Abrir `http://localhost:8000`

## Uso

1. **Configuración inicial**: Ajusta `config.yaml`
   - `interfaz`: eth0/enp1s0/etc
   - `whitelist`: Rango de confianza
   - `multiplicador_alerta`: Sensibilidad (3.0 conservador)

2. **Ejecución**: 
   ```bash
   sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0
   ```

3. **Panel web**:
   - Gráficos PPS realtime
   - Lista top atacantes
   - Alertas con tipo de ataque
   - Conteo bloqueados

4. **Comandos manuales**:
   ```bash
   sudo ipset list ddos_blacklist     # Ver bloqueados
   sudo ipset flush ddos_blacklist    # Limpiar todos
   ```

## Endpoints API

| Endpoint | Descripción | Formato |
|----------|-------------|---------|
| `/estadisticas` | Top IPs por PPS | JSON |
| `/bloqueados` | IPs en blacklist | JSON |
| `/alertas` | Alertas recientes | JSON |
| `/ws` | WebSocket realtime | - |

## Arquitectura Técnica

Ver [docs/arquitectura.md](docs/arquitectura.md)

```
Red → nftables DROP (ipset lookup) → Servidor
         ↑
      Scapy → Detector → Mitigador → ipset add
         ↓
     FastAPI + WebSocket → Panel HTML/JS
```

## Verificación y Pruebas

**Simular ataque** (otro terminal):
```bash
sudo hping3 --flood --icmp -i u1 192.168.1.100  # ICMP flood
sudo hping3 --flood -S -p 80 -i u1 192.168.1.100 # SYN flood
```

**Monitorear**:
```bash
sudo ipset list ddos_blacklist
sudo nft list ruleset
journalctl -f  # Logs sistema
```

## Consideraciones de Seguridad

* Requiere root (sniff + nftables)
* Whitelist IPs legítimas
* Baseline aprende tráfico normal (~5min)
* Timeout evita bloqueos permanentes
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
**Desarrollado para producción con estándares empresariales.**
