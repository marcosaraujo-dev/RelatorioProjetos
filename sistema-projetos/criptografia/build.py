"""
Script para gerar o executável da aplicação de gerenciamento de projetos
Uso: python build.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_requirements():
    """Verificar se todas as dependências estão instaladas"""
    print("🔍 Verificando dependências...")
    
    try:
        import PyInstaller
        print("✅ PyInstaller encontrado")
    except ImportError:
        print("❌ PyInstaller não encontrado. Instalando...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Verificar se o requirements.txt existe
    if not os.path.exists("requirements.txt"):
        print("❌ requirements.txt não encontrado!")
        return False
    
    print("✅ Todos os requisitos verificados")
    return True

def install_dependencies():
    """Instalar dependências do requirements.txt"""
    print("📦 Instalando dependências...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependências instaladas com sucesso")
        return True
    except subprocess.CalledProcessError:
        print("❌ Erro ao instalar dependências")
        return False

def clean_build():
    """Limpar arquivos de build anteriores"""
    print("🧹 Limpando arquivos de build anteriores...")
    
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = ["*.spec"]
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"   Removido: {dir_name}")
    
    # Remover arquivos .spec
    for spec_file in Path(".").glob("*.spec"):
        spec_file.unlink()
        print(f"   Removido: {spec_file}")

def create_executable():
    """Criar o executável usando PyInstaller"""
    print("🔨 Criando executável...")
    
    # Comando PyInstaller
    cmd = [
        "pyinstaller",
        "--onefile",                    # Arquivo único
        "--windowed",                   # Não mostrar console (Windows)
        "--noconsole",                  # Não mostrar console
        "--add-data", "templates;templates",  # Incluir templates
        "--add-data", "static;static",        # Incluir arquivos estáticos (se houver)
        "--name", "SistemaProjetos",          # Nome do executável
        "--icon", "icon.ico",               # Ícone (opcional)
        "--distpath", "dist",               # Pasta de saída
        "--workpath", "build",              # Pasta de trabalho
        "app.py"                            # Arquivo principal
    ]
    
    # Remover ícone se não existir
    if not os.path.exists("icon.ico"):
        cmd = [item for item in cmd if item != "--icon" and item != "icon.ico"]
    
    try:
        subprocess.check_call(cmd)
        print("✅ Executável criado com sucesso!")
        return True
    except subprocess.CalledProcessError:
        print("❌ Erro ao criar executável")
        return False

def create_installer_script():
    """Criar script de instalação/configuração"""
    print("📋 Criando script de instalação...")
    
    installer_content = """@echo off
echo ====================================
echo   Sistema de Projetos - Instalacao
echo ====================================
echo.

REM Verificar se o ODBC Driver está instalado
echo Verificando ODBC Driver for SQL Server...

REG QUERY "HKEY_LOCAL_MACHINE\\SOFTWARE\\ODBC\\ODBCINST.INI\\ODBC Driver 17 for SQL Server" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo AVISO: ODBC Driver 17 for SQL Server nao encontrado!
    echo.
    echo Para que o sistema funcione corretamente, voce precisa instalar:
    echo "Microsoft ODBC Driver 17 for SQL Server"
    echo.
    echo Download: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
    echo.
    pause
) else (
    echo ODBC Driver encontrado!
)

echo.
echo Executando Sistema de Projetos...
echo.

REM Executar o sistema
SistemaProjetos.exe

pause
"""
    
    with open("dist/Instalar_e_Executar.bat", "w", encoding="utf-8") as f:
        f.write(installer_content)
    
    print("✅ Script de instalação criado: dist/Instalar_e_Executar.bat")

def create_readme():
    """Criar arquivo README para distribuição"""
    print("📄 Criando arquivo README...")
    
    readme_content = """# Sistema de Projetos

## Como usar:

1. **Primeiro uso:**
   - Execute o arquivo "Instalar_e_Executar.bat" como Administrador
   - Isso verificará se o ODBC Driver está instalado

2. **Uso normal:**
   - Execute "SistemaProjetos.exe"
   - O sistema abrirá automaticamente no seu navegador
   - Acesse: http://localhost:5000

## Recursos:

- ✅ Dashboard com estatísticas dos projetos
- ✅ Gráfico de Gantt interativo
- ✅ Relatórios de Épicos com filtros
- ✅ Relatórios de SubTasks com filtros
- ✅ Exportação para CSV
- ✅ Interface responsiva

## Requisitos:

- Windows 7/8/10/11
- Microsoft ODBC Driver 17 for SQL Server
- Conexão com o banco de dados SQL Server

## Suporte:

Em caso de problemas:
1. Verifique se o ODBC Driver está instalado
2. Verifique a conexão com o banco de dados
3. Verifique se a porta 5000 não está sendo usada por outro programa

---
Desenvolvido em Python + Flask + Plotly
"""
    
    with open("dist/README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print("✅ README criado: dist/README.txt")

def main():
    """Função principal do build"""
    print("🚀 Iniciando build do Sistema de Projetos")
    print("=" * 50)
    
    # Verificar se estamos no diretório correto
    if not os.path.exists("app.py"):
        print("❌ app.py não encontrado! Execute este script na pasta do projeto.")
        return False
    
    # Verificar requisitos
    if not check_requirements():
        return False
    
    # Instalar dependências
    if not install_dependencies():
        return False
    
    # Limpar build anterior
    clean_build()
    
    # Criar executável
    if not create_executable():
        return False
    
    # Criar arquivos auxiliares
    create_installer_script()
    create_readme()
    
    # Verificar se o executável foi criado
    exe_path = "dist/SistemaProjetos.exe"
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"✅ Build concluído com sucesso!")
        print(f"📁 Arquivo criado: {exe_path}")
        print(f"📏 Tamanho: {size_mb:.1f} MB")
        print("=" * 50)
        print("🎉 Pronto para distribuição!")
        print("📂 Todos os arquivos estão na pasta 'dist/'")
        return True
    else:
        print("❌ Executável não foi criado")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✨ Build finalizado com sucesso!")
        input("\nPressione Enter para sair...")
    else:
        print("\n💥 Build falhou!")
        input("\nPressione Enter para sair...")
        sys.exit(1)