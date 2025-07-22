"""
Script para verificar se todas as dependências estão instaladas
Execute: python check_dependencies.py
"""

import sys
import subprocess

def check_module(module_name, install_name=None):
    """Verificar se um módulo está instalado"""
    if install_name is None:
        install_name = module_name
    
    try:
        __import__(module_name)
        print(f"✅ {module_name} - OK")
        return True
    except ImportError:
        print(f"❌ {module_name} - NÃO INSTALADO")
        print(f"   Para instalar: pip install {install_name}")
        return False

def install_missing_modules():
    """Instalar módulos faltantes automaticamente"""
    missing_modules = []
    
    modules_to_check = [
        ('flask', 'Flask'),
        ('pandas', 'pandas'),
        ('pyodbc', 'pyodbc'),
        ('plotly', 'plotly'),
        ('cryptography', 'cryptography'),
        ('werkzeug', 'Werkzeug'),
        ('jinja2', 'Jinja2')
    ]
    
    print("🔍 Verificando dependências...")
    print("=" * 40)
    
    for module_name, install_name in modules_to_check:
        if not check_module(module_name, install_name):
            missing_modules.append(install_name)
    
    if missing_modules:
        print("\n" + "=" * 40)
        print(f"📦 Encontrados {len(missing_modules)} módulos faltantes")
        
        response = input("\n🤔 Deseja instalar automaticamente? (s/n): ")
        
        if response.lower() in ['s', 'sim', 'y', 'yes']:
            print("\n🚀 Instalando módulos...")
            
            for module in missing_modules:
                try:
                    print(f"Instalando {module}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", module])
                    print(f"✅ {module} instalado com sucesso!")
                except subprocess.CalledProcessError:
                    print(f"❌ Erro ao instalar {module}")
            
            print("\n🔄 Verificando novamente...")
            return check_all_modules()
        else:
            print("\n📋 Para instalar manualmente, execute:")
            print(f"pip install {' '.join(missing_modules)}")
            return False
    else:
        print("\n🎉 Todas as dependências estão instaladas!")
        return True

def check_all_modules():
    """Verificar todos os módulos novamente"""
    modules_to_check = [
        ('flask', 'Flask'),
        ('pandas', 'pandas'),
        ('pyodbc', 'pyodbc'),
        ('plotly', 'plotly'),
        ('cryptography', 'cryptography')
    ]
    
    all_ok = True
    for module_name, install_name in modules_to_check:
        if not check_module(module_name, install_name):
            all_ok = False
    
    return all_ok

def check_python_version():
    """Verificar versão do Python"""
    version = sys.version_info
    print(f"🐍 Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print("⚠️  AVISO: Recomendado Python 3.7 ou superior")
        return False
    else:
        print("✅ Versão do Python compatível")
        return True

def main():
    print("🔧 Verificador de Dependências - Sistema de Projetos")
    print("=" * 50)
    
    # Verificar versão do Python
    python_ok = check_python_version()
    print()
    
    # Verificar e instalar módulos
    modules_ok = install_missing_modules()
    
    print("\n" + "=" * 50)
    
    if python_ok and modules_ok:
        print("🎉 TUDO PRONTO!")
        print("Agora você pode executar: python app.py")
        
        # Testar importações críticas
        print("\n🧪 Testando importações...")
        try:
            from flask import Flask
            import pandas as pd
            import plotly
            print("✅ Teste de importação bem-sucedido!")
        except Exception as e:
            print(f"❌ Erro no teste: {e}")
            
    else:
        print("❌ EXISTEM PROBLEMAS")
        print("Resolva os problemas acima antes de continuar")
    
    print("\n💡 DICAS:")
    print("- Se pip não funcionar, tente: python -m pip install ...")
    print("- Use ambiente virtual para evitar conflitos")
    print("- No Windows, certifique-se que Python está no PATH")

if __name__ == "__main__":
    main()
    input("\nPressione Enter para sair...")