#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de diagnóstico para verificar problemas en DDoS Mitigator
Ejecutar: python3 diagnostico.py
"""
import os
import sys
import importlib.util

def check_file(path, title):
    """Verificar si archivo existe."""
    exists = os.path.exists(path)
    status = "[OK]" if exists else "[MISSING]"
    print(f"{status} {title}: {path}")
    return exists

def check_imports():
    """Verificar imports principales."""
    print("\n[CHECK] Verificando imports...")
    imports = [
        ("fastapi", "FastAPI"),
        ("scapy", "Scapy"),
        ("pyyaml", "PyYAML"),
        ("geoip2", "GeoIP2"),
        ("aiofiles", "Aiofiles"),
    ]
    
    for pkg, name in imports:
        try:
            importlib.import_module(pkg)
            print(f"  [OK] {name}")
        except ImportError as e:
            print(f"  [ERROR] {name}: {e}")
            return False
    return True

def check_structure():
    """Verificar estructura de carpetas."""
    print("\n[CHECK] Estructura de carpetas:")
    folders = [
        "backend",
        "frontend",
        "scripts",
        "docs",
        "data",
        "logs",
    ]
    
    for folder in folders:
        check_file(folder, f"Carpeta {folder}")

def check_files():
    """Verificar archivos clave."""
    print("\n[CHECK] Archivos clave:")
    files = [
        ("backend/main.py", "API principal"),
        ("backend/captura.py", "Capturador Scapy"),
        ("backend/detector.py", "Detector anomalías"),
        ("backend/mitigacion.py", "Mitigador ipset"),
        ("backend/enriquecimiento.py", "Enriquecedor GeoIP"),
        ("frontend/index.html", "Frontend HTML"),
        ("frontend/app.js", "Frontend JavaScript"),
        ("frontend/estilos.css", "Frontend CSS"),
        ("config.yaml", "Configuración"),
        ("requirements.txt", "Dependencias"),
    ]
    
    all_exist = True
    for file_path, desc in files:
        if not check_file(file_path, desc):
            all_exist = False
    
    return all_exist

def check_python_version():
    """Verificar versión de Python."""
    print(f"\n[CHECK] Python version: {sys.version}")
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"  [OK] Python {version.major}.{version.minor} es compatible")
        return True
    else:
        print(f"  [WARNING] Se recomienda Python 3.9+")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("DDoS Mitigator - Diagnóstico de Sistema")
    print("=" * 60)
    
    check_python_version()
    check_structure()
    files_ok = check_files()
    imports_ok = check_imports()
    
    print("\n" + "=" * 60)
    if files_ok and imports_ok:
        print("[OK] Diagnóstico completado. Sistema listo.")
    else:
        print("[WARNING] Se encontraron problemas. Ver arriba.")
    print("=" * 60)
