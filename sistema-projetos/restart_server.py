"""
Script para reiniciar o servidor Flask
Execute: python restart_server.py
"""

import os
import sys
import time
import subprocess

def restart_server():
    """Reiniciar o servidor Flask"""
    print("🔄 Reiniciando servidor Flask...")
    
    # Matar processos Python que possam estar rodando na porta 5000
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/f', '/im', 'python.exe'], 
                         capture_output=True, check=False)
        else:  # Linux/Mac
            subprocess.run(['pkill', '-f', 'python'], 
                         capture_output=True, check=False)
    except:
        pass
    
    print("⏳ Aguardando 2 segundos...")
    time.sleep(2)
    
    print("🚀 Iniciando servidor...")
    
    # Executar app.py
    try:
        subprocess.run([sys.executable, 'app.py'])
    except KeyboardInterrupt:
        print("\n⏹️ Servidor parado pelo usuário")
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")

if __name__ == "__main__":
    restart_server()