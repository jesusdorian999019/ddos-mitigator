#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests básicos para DDoS Mitigator.
Ejecutar con: pytest test_main.py -v
"""
import pytest
import asyncio
from backend.utils import IPValidator, ThreadSafeLRUCache
from backend.config import Config
from backend.captura import Capturador


class TestIPValidator:
    """Tests para validación de IPs."""
    
    def test_ipv4_valida(self):
        assert IPValidator.es_ipv4("192.168.1.1") == True
        assert IPValidator.es_ipv4("10.0.0.1") == True
        assert IPValidator.es_ipv4("255.255.255.255") == True
    
    def test_ipv4_invalida(self):
        assert IPValidator.es_ipv4("256.256.256.256") == False
        assert IPValidator.es_ipv4("not.an.ip.address") == False
        assert IPValidator.es_ipv4("192.168.1") == False
    
    def test_ipv6_valida(self):
        assert IPValidator.es_ipv6("::1") == True
        assert IPValidator.es_ipv6("fe80::1") == True
    
    def test_cidr_valida(self):
        assert IPValidator.es_cidr("192.168.0.0/24") == True
        assert IPValidator.es_cidr("10.0.0.0/8") == True
    
    def test_cidr_invalida(self):
        assert IPValidator.es_cidr("192.168.0.0/33") == False
        assert IPValidator.es_cidr("not/cidr") == False


class TestLRUCache:
    """Tests para LRU cache."""
    
    def test_put_get(self):
        cache = ThreadSafeLRUCache(max_size=2)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_evict(self):
        cache = ThreadSafeLRUCache(max_size=2)
        cache.put("key1", "val1")
        cache.put("key2", "val2")
        cache.put("key3", "val3")  # key1 debe ser evicted
        assert cache.get("key1") is None
        assert cache.get("key2") == "val2"
    
    def test_clear(self):
        cache = ThreadSafeLRUCache()
        cache.put("key", "value")
        cache.clear()
        assert cache.get("key") is None


class TestConfig:
    """Tests para configuración."""
    
    def test_defaults(self):
        config = Config(config_path='/no/existe.yaml')
        assert config.get('interfaz') == 'eth0'
        assert config.get('puerto_api') == 8000
        assert config.get('baseline_pps') == 100
    
    def test_update_config(self):
        config = Config(config_path='/no/existe.yaml')
        config.update('baseline_pps', 200)
        assert config.get('baseline_pps') == 200
    
    def test_invalid_value_rejected(self):
        config = Config(config_path='/no/existe.yaml')
        with pytest.raises(ValueError):
            config.update('baseline_pps', -1)  # Debe ser > 0


class TestCapturador:
    """Tests para capturador."""
    
    def test_pps_calculation(self):
        cap = Capturador()
        # Sin paquetes = PPS bajo
        assert cap.pps_por_ip("192.168.1.1") >= 1
    
    def test_top_ips_empty(self):
        cap = Capturador()
        top = cap.top_ips(10)
        assert isinstance(top, list)
        assert len(top) == 0  # Sin captura aún


@pytest.mark.asyncio
async def test_api_health():
    """Test endpoint /health."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'


@pytest.mark.asyncio
async def test_api_stats():
    """Test endpoint /stats."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    client = TestClient(app)
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert 'captura' in data
    assert 'detector' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
