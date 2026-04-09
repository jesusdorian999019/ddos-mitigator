# Quick Fix - DDoS Mitigator Python 3.13 Compatibility

## Problema

Error al ejecutar:
```
TypeError: L2Socket._init_() got an unexpected keyword argument 'threaded'
```

## Causa

- Scapy 2.5.0 no es totalmente compatible con Python 3.13
- El parámetro `threaded` fue removido en versiones más recientes
- Se instaló una versión antigua de Scapy

## Soluciones Implementadas

### 1. Actualización de captura.py
Se removió el parámetro `threaded=False` que no es soportado en Scapy 2.5.0+

**Antes**:
```python
sniff(iface=self.interfaz, prn=packet_handler, filter=filtro,
      store=False, threaded=False)
```

**Después**:
```python
sniff(iface=self.interfaz, prn=packet_handler, filter=filtro,
      store=False)
```

### 2. Actualización de requirements.txt
Scapy ahora requiere versión >= 2.6.0 (compatible with Python 3.13)

**Antes**:
```
scapy==2.5.0
```

**Después**:
```
scapy>=2.6.0
```

## Como Aplicar la Fix

Si ya clonaste el repositorio y tienes el error:

```bash
# 1. Activar venv
source venv/bin/activate

# 2. Actualizar paquetes
pip install --upgrade pip
pip install -r requirements.txt

# 3. Reintentar
sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Si Clonas de Cero (Recomendado)

```bash
# Clonar
git clone https://github.com/jesusdorian999019/ddos-mitigator.git
cd ddos-mitigator

# Setup (ya tiene las fixes)
chmod +x scripts/setup.sh
sudo ./scripts/setup.sh

# Editar config
nano config.yaml

# Ejecutar
source venv/bin/activate
sudo venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Requisitos Actuales

- Python: 3.9+ (probado en 3.11, 3.12, 3.13)
- Scapy: >= 2.6.0
- FastAPI: 0.104.1+
- Uvicorn: 0.24.0+

## Notas GeoIP

Si ves warnings sobre GeoIP:
```
WARNING - GeoLite2-City.mmdb no encontrado
WARNING - GeoLite2-ASN.mmdb no encontrado
```

Es normal. El sistema funciona sin GeoIP. Si quieres activar:

1. Descargar desde: https://www.maxmind.com/en/geoip2/geolite2
2. Copiar a: `data/GeoLite2-City.mmdb` y `data/GeoLite2-ASN.mmdb`

El warning desaparecerá en próxima ejecución.

---

**Status**: Fixed for Python 3.13 compatibility
**Last Updated**: 2024
