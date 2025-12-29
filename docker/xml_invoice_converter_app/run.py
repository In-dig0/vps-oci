# run.py
"""
Script di lancio per l'applicazione XML Invoice Converter.
Uso: python run.py
"""
import subprocess
import sys
import os
from pathlib import Path

def main():
    """Avvia l'applicazione NiceGUI."""
    # Rileva ambiente
    in_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'
    
    # Verifica che il file esista
    app_file = Path("src/xml_invoice_converter.py")  
    if not app_file.exists():
        print(f"❌ Errore: File {app_file} non trovato!")
        sys.exit(1)
    
    # Configura parametri
    server_address = "0.0.0.0" if in_docker else "localhost"
    server_port = os.getenv("PORT", "8502")
    
    print(f"🚀 Avvio XML Invoice Converter su {server_address}:{server_port}")
    print(f"📁 File: {app_file}")
    print(f"🐳 Docker: {'Sì' if in_docker else 'No'}")
    
    # Avvia NiceGUI con parametri
    subprocess.run([
        sys.executable,
        str(app_file),
        f"--host={server_address}",
        f"--port={server_port}"
    ])

if __name__ == "__main__":
    main()
