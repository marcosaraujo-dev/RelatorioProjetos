"""
Instalador de dependências com relatório completo
Lê requirements.txt e gera relatório de instalação
Execute: python install_requirements.py
"""

import sys
import subprocess
import os
import time
from datetime import datetime

class InstallationReporter:
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
        
    def start_installation(self):
        """Iniciar processo de instalação"""
        self.start_time = datetime.now()
        print("🚀 Instalador de Dependências - Sistema de Projetos")
        print("=" * 60)
        print(f"📅 Início: {self.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"🐍 Python: {sys.version}")
        print(f"📁 Diretório: {os.getcwd()}")
        print("=" * 60)
    
    def check_requirements_file(self):
        """Verificar se requirements.txt existe"""
        if not os.path.exists('requirements.txt'):
            print("❌ ERRO: Arquivo requirements.txt não encontrado!")
            print("📝 Criando requirements.txt básico...")
            self.create_basic_requirements()
            return True
        else:
            print("✅ requirements.txt encontrado")
            return True
    
    def create_basic_requirements(self):
        """Criar requirements.txt básico se não existir"""
        basic_requirements = """Flask==2.3.3
pandas==2.0.3
pyodbc==4.0.39
plotly==5.17.0
cryptography==41.0.4
Werkzeug==2.3.7
Jinja2==3.1.2
MarkupSafe==2.1.3
itsdangerous==2.1.2
click==8.1.7
blinker==1.6.3
numpy==1.24.3
python-dateutil==2.8.2
pytz==2023.3
six==1.16.0
tenacity==8.2.3
packaging==23.1"""
        
        with open('requirements.txt', 'w') as f:
            f.write(basic_requirements)
        print("✅ requirements.txt criado com dependências básicas")
    
    def read_requirements(self):
        """Ler requirements.txt e extrair pacotes"""
        packages = []
        try:
            with open('requirements.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extrair nome do pacote (antes de == ou >=)
                        package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0]
                        packages.append({
                            'name': package_name,
                            'requirement': line,
                            'status': 'pending'
                        })
            
            print(f"📦 Encontrados {len(packages)} pacotes em requirements.txt")
            return packages
        except Exception as e:
            print(f"❌ Erro ao ler requirements.txt: {e}")
            return []
    
    def install_requirements(self):
        """Instalar dependências via pip install -r requirements.txt"""
        print("\n🔄 Iniciando instalação via requirements.txt...")
        print("-" * 40)
        
        try:
            # Executar pip install -r requirements.txt
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                print("✅ Instalação via requirements.txt concluída!")
                return True, result.stdout, result.stderr
            else:
                print("⚠️ Instalação via requirements.txt teve problemas")
                return False, result.stdout, result.stderr
                
        except subprocess.TimeoutExpired:
            print("⏰ Timeout na instalação (5 minutos)")
            return False, "", "Timeout na instalação"
        except Exception as e:
            print(f"❌ Erro na instalação: {e}")
            return False, "", str(e)
    
    def verify_installations(self, packages):
        """Verificar quais pacotes foram instalados com sucesso"""
        print("\n🔍 Verificando instalações...")
        print("-" * 40)
        
        success_count = 0
        failed_packages = []
        
        for package in packages:
            try:
                # Tentar importar o pacote
                package_name = package['name'].lower()
                
                # Mapeamento de nomes especiais
                import_names = {
                    'pillow': 'PIL',
                    'beautifulsoup4': 'bs4',
                    'pyyaml': 'yaml',
                    'python-dateutil': 'dateutil',
                    'markupsafe': 'markupsafe'
                }
                
                import_name = import_names.get(package_name, package_name)
                
                __import__(import_name)
                
                package['status'] = 'success'
                print(f"✅ {package['name']} - OK")
                success_count += 1
                
            except ImportError:
                package['status'] = 'failed'
                print(f"❌ {package['name']} - FALHOU")
                failed_packages.append(package)
            except Exception as e:
                package['status'] = 'error'
                print(f"⚠️ {package['name']} - ERRO: {e}")
                failed_packages.append(package)
        
        return success_count, failed_packages
    
    def retry_failed_installations(self, failed_packages):
        """Tentar reinstalar pacotes que falharam"""
        if not failed_packages:
            return []
        
        print(f"\n🔄 Tentando reinstalar {len(failed_packages)} pacotes que falharam...")
        print("-" * 40)
        
        still_failed = []
        
        for package in failed_packages:
            try:
                print(f"Reinstalando {package['name']}...")
                result = subprocess.run([
                    sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", package['requirement']
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    # Tentar importar novamente
                    try:
                        package_name = package['name'].lower()
                        import_names = {
                            'pillow': 'PIL',
                            'beautifulsoup4': 'bs4',
                            'pyyaml': 'yaml',
                            'python-dateutil': 'dateutil',
                            'markupsafe': 'markupsafe'
                        }
                        import_name = import_names.get(package_name, package_name)
                        __import__(import_name)
                        
                        package['status'] = 'success_retry'
                        print(f"✅ {package['name']} - SUCESSO na segunda tentativa")
                    except ImportError:
                        package['status'] = 'failed_retry'
                        still_failed.append(package)
                        print(f"❌ {package['name']} - AINDA FALHOU")
                else:
                    package['status'] = 'failed_retry'
                    still_failed.append(package)
                    print(f"❌ {package['name']} - ERRO na reinstalação")
                    
            except Exception as e:
                package['status'] = 'error_retry'
                still_failed.append(package)
                print(f"⚠️ {package['name']} - ERRO: {e}")
        
        return still_failed
    
    def generate_report(self, packages, install_success, install_output, install_error):
        """Gerar relatório final detalhado"""
        self.end_time = datetime.now()
        duration = self.end_time - self.start_time
        
        print("\n" + "=" * 60)
        print("📊 RELATÓRIO FINAL DE INSTALAÇÃO")
        print("=" * 60)
        
        # Estatísticas gerais
        total_packages = len(packages)
        successful = len([p for p in packages if p['status'] in ['success', 'success_retry']])
        failed = len([p for p in packages if 'failed' in p['status'] or 'error' in p['status']])
        
        print(f"📅 Data: {self.end_time.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"⏱️ Duração: {duration.total_seconds():.1f} segundos")
        print(f"📦 Total de pacotes: {total_packages}")
        print(f"✅ Instalados com sucesso: {successful}")
        print(f"❌ Falharam: {failed}")
        print(f"📈 Taxa de sucesso: {(successful/total_packages*100):.1f}%")
        
        # Status da instalação geral
        print(f"\n🔧 Status da instalação via requirements.txt:")
        if install_success:
            print("✅ SUCESSO - requirements.txt instalado sem erros críticos")
        else:
            print("⚠️ PROBLEMAS - Houve erros na instalação via requirements.txt")
        
        # Detalhes por pacote
        print(f"\n📋 DETALHES POR PACOTE:")
        print("-" * 40)
        
        success_packages = [p for p in packages if p['status'] in ['success', 'success_retry']]
        failed_packages = [p for p in packages if 'failed' in p['status'] or 'error' in p['status']]
        
        if success_packages:
            print("✅ PACOTES INSTALADOS COM SUCESSO:")
            for package in success_packages:
                status_icon = "🔄" if package['status'] == 'success_retry' else "✅"
                print(f"   {status_icon} {package['name']}")
        
        if failed_packages:
            print("\n❌ PACOTES QUE FALHARAM:")
            for package in failed_packages:
                print(f"   ❌ {package['name']} - {package['requirement']}")
                print(f"      Status: {package['status']}")
        
        # Próximos passos
        print(f"\n🎯 PRÓXIMOS PASSOS:")
        if failed == 0:
            print("🎉 PERFEITO! Todas as dependências foram instaladas!")
            print("✅ Você pode executar: python app.py")
        else:
            print("⚠️ Algumas dependências falharam:")
            print("1. Verifique se você tem permissões de administrador")
            print("2. Tente instalar os pacotes faltantes manualmente:")
            for package in failed_packages:
                print(f"   pip install {package['requirement']}")
            print("3. Verifique se você tem as dependências do sistema necessárias")
        
        # Salvar relatório em arquivo
        self.save_report_to_file(packages, successful, failed, duration, install_output, install_error)
        
        return successful == total_packages
    
    def save_report_to_file(self, packages, successful, failed, duration, install_output, install_error):
        """Salvar relatório detalhado em arquivo"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'installation_report_{timestamp}.txt'
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("RELATÓRIO DE INSTALAÇÃO - SISTEMA DE PROJETOS\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"Duração: {duration.total_seconds():.1f} segundos\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Diretório: {os.getcwd()}\n\n")
                
                f.write("ESTATÍSTICAS:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total de pacotes: {len(packages)}\n")
                f.write(f"Sucessos: {successful}\n")
                f.write(f"Falhas: {failed}\n")
                f.write(f"Taxa de sucesso: {(successful/len(packages)*100):.1f}%\n\n")
                
                f.write("DETALHES DOS PACOTES:\n")
                f.write("-" * 25 + "\n")
                for package in packages:
                    f.write(f"{package['name']} ({package['requirement']}) - {package['status']}\n")
                
                f.write(f"\nSAÍDA DA INSTALAÇÃO:\n")
                f.write("-" * 25 + "\n")
                f.write(install_output)
                
                if install_error:
                    f.write(f"\nERROS:\n")
                    f.write("-" * 10 + "\n")
                    f.write(install_error)
            
            print(f"💾 Relatório salvo em: {filename}")
            
        except Exception as e:
            print(f"⚠️ Não foi possível salvar o relatório: {e}")

def main():
    """Função principal"""
    reporter = InstallationReporter()
    
    # Iniciar processo
    reporter.start_installation()
    
    # Verificar se requirements.txt existe
    if not reporter.check_requirements_file():
        return
    
    # Ler pacotes do requirements.txt
    packages = reporter.read_requirements()
    if not packages:
        print("❌ Nenhum pacote encontrado para instalar")
        return
    
    # Instalar via requirements.txt
    install_success, install_output, install_error = reporter.install_requirements()
    
    # Verificar instalações
    success_count, failed_packages = reporter.verify_installations(packages)
    
    # Tentar reinstalar pacotes que falharam
    if failed_packages:
        still_failed = reporter.retry_failed_installations(failed_packages)
    
    # Gerar relatório final
    all_success = reporter.generate_report(packages, install_success, install_output, install_error)
    
    # Pergunta se quer testar a aplicação
    if all_success:
        print("\n🚀 TUDO PRONTO!")
        response = input("Deseja testar a aplicação agora? (s/n): ")
        if response.lower() in ['s', 'sim', 'y', 'yes']:
            print("Iniciando aplicação...")
            try:
                subprocess.run([sys.executable, "app.py"], timeout=5)
            except subprocess.TimeoutExpired:
                print("Aplicação iniciada em segundo plano")
            except Exception as e:
                print(f"Erro ao iniciar aplicação: {e}")

if __name__ == "__main__":
    main()
    input("\nPressione Enter para sair...")