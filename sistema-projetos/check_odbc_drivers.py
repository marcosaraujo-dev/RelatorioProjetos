"""
Script para verificar drivers ODBC disponíveis
Execute: python check_odbc_drivers.py
"""

import pyodbc
import sys

def check_odbc_drivers():
    """Verificar drivers ODBC disponíveis no sistema"""
    print("🔍 Verificando drivers ODBC disponíveis...")
    print("=" * 50)
    
    drivers = pyodbc.drivers()
    
    if not drivers:
        print("❌ Nenhum driver ODBC encontrado!")
        print("\n💡 SOLUÇÃO:")
        print("1. Instale o ODBC Driver 17 for SQL Server")
        print("2. URL: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server")
        return False
    
    print(f"📦 Encontrados {len(drivers)} drivers:")
    print("-" * 30)
    
    sql_server_drivers = []
    
    for driver in drivers:
        if "SQL Server" in driver:
            sql_server_drivers.append(driver)
            print(f"✅ {driver}")
        else:
            print(f"📌 {driver}")
    
    print("\n" + "=" * 50)
    
    if sql_server_drivers:
        print(f"🎯 Drivers SQL Server encontrados: {len(sql_server_drivers)}")
        
        # Testar qual é o melhor
        print("\n🧪 Testando compatibilidade:")
        
        recommended_order = [
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server", 
            "ODBC Driver 11 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]
        
        best_driver = None
        for rec_driver in recommended_order:
            if rec_driver in sql_server_drivers:
                best_driver = rec_driver
                print(f"🏆 RECOMENDADO: {rec_driver}")
                break
        
        if not best_driver:
            best_driver = sql_server_drivers[0]
            print(f"⚠️ USANDO: {best_driver} (não é o ideal)")
        
        print(f"\n✅ Driver que será usado: {best_driver}")
        return True, best_driver
    else:
        print("❌ Nenhum driver SQL Server encontrado!")
        print("\n💡 INSTALE:")
        print("- ODBC Driver 17 for SQL Server (RECOMENDADO)")
        print("- Compatível com SQL Server 2014")
        return False, None

def test_connection_with_driver(driver_name):
    """Testar conexão com um driver específico"""
    print(f"\n🔌 Testando conexão com {driver_name}...")
    
    # Credenciais de teste (substitua pelos seus dados)
    server = "52.234.210.220"
    database = "jira_bi"
    username = "marcos.araujo"
    password = "Pwb$f592.MaJ"
    
    connection_string = (
        f"DRIVER={{{driver_name}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=10;"
    )
    
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        conn.close()
        
        print("✅ CONEXÃO BEM-SUCEDIDA!")
        print(f"   Driver: {driver_name}")
        print(f"   Servidor: {server}")
        print(f"   Database: {database}")
        return True
        
    except Exception as e:
        print(f"❌ ERRO NA CONEXÃO: {str(e)}")
        return False

def download_odbc_driver():
    """Instruções para baixar o driver ODBC"""
    print("\n📥 COMO INSTALAR O ODBC DRIVER 17:")
    print("=" * 40)
    print("1. Acesse: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server")
    print("2. Baixe: 'ODBC Driver 17 for SQL Server'")
    print("3. Execute como Administrador")
    print("4. Reinicie o computador")
    print("5. Execute este script novamente")
    
    print("\n🔗 LINK DIRETO PARA DOWNLOAD:")
    print("https://go.microsoft.com/fwlink/?linkid=2249006")

def main():
    """Função principal"""
    print("🚀 Verificador de Drivers ODBC - Sistema de Projetos")
    print("=" * 60)
    
    # Verificar drivers
    result = check_odbc_drivers()
    
    if isinstance(result, tuple) and result[0]:
        success, best_driver = result
        
        # Testar conexão com o melhor driver
        print("\n" + "=" * 60)
        connection_ok = test_connection_with_driver(best_driver)
        
        if connection_ok:
            print("\n🎉 TUDO CONFIGURADO CORRETAMENTE!")
            print("✅ Você pode executar: python app.py")
        else:
            print("\n⚠️ DRIVER OK, MAS CONEXÃO FALHOU")
            print("Verifique:")
            print("- IP do servidor está correto")
            print("- Usuário e senha estão corretos") 
            print("- Firewall/rede permite conexão")
            print("- SQL Server está rodando")
    else:
        print("\n❌ PRECISA INSTALAR DRIVER ODBC")
        download_odbc_driver()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
    input("\nPressione Enter para sair...")