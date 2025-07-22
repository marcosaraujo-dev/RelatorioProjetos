import pyodbc
from cryptography.fernet import Fernet
import base64
import os

class DatabaseManager:
    def __init__(self):
        # Chave de criptografia fixa
        key = b'O-zOaRv7FLzjh6nzVqRhTj_eQkRmPkZyPb3t-1agal0='  #chave
        self.cipher = Fernet(key)
        
        # Credenciais criptografadas (você deve criptografar suas credenciais reais)
        self.encrypted_server = b'gAAAAABofrqfGwYc1k2csm1pk_kkgRykq6TsLBedxRnOEtA5IN1iM8Bh70FUgTJ_Nr3Yl1IJtCGFGy4oHqCnBoey2wdZjIuYGg=='
        self.encrypted_username = b'gAAAAABofrqfuJPV5bjgAlJxp3iquOzrtrlKVawGhMF4BeQ1dUZdB4fAJG9WdGo2ryiWtyrTCCfHvWGF_MOIoOyjtmAnMvVnZg=='
        self.encrypted_password = b'gAAAAABofrqfFjSm3-W02onTqMjNtPlVISR_Rs7wcE0teYHyI2Hm_oUMqkBm-eF4IdGdWbUS7FHWPeyXunn15bOyiC76TSFqTA=='
        self.encrypted_database = b'gAAAAABofrqfAEfMtkGM6LtnEPLRQ8UIA5pBy_FgbiJOK7fQaLzeG3-_pQJuDSGJxxqyv-EpXBdZfd_Ku4J1-v7WLFDPo9J9uA=='
        
        # Para este exemplo, vou usar as credenciais diretas (REMOVA EM PRODUÇÃO)
        self.server = "192.168.0.1"
        self.username = "marcos.araujo" 
        self.password = "1234"
        self.database = "project_bi"
    
    def encrypt_credentials(self, server, username, password):
        """
        Método para criptografar credenciais (use uma vez para gerar as strings criptografadas)
        """
        encrypted_server = self.cipher.encrypt(server.encode())
        encrypted_username = self.cipher.encrypt(username.encode()) 
        encrypted_password = self.cipher.encrypt(password.encode())
        encrypted_database = self.cipher.encrypt(self.database.encode())
        
        print("Credenciais criptografadas:")
        print(f"Server: {encrypted_server}")
        print(f"Username: {encrypted_username}")
        print(f"Password: {encrypted_password}")
        print(f"Database: {encrypted_database}")
        
        return encrypted_server, encrypted_username, encrypted_password
    
    def decrypt_credentials(self):
        """Descriptografar credenciais"""
        try:
            # Em produção, use estas linhas:
            server = self.cipher.decrypt(self.encrypted_server).decode()
            username = self.cipher.decrypt(self.encrypted_username).decode()
            password = self.cipher.decrypt(self.encrypted_password).decode()
            database = self.cipher.decrypt(self.encrypted_database).decode()
            # Para desenvolvimento (REMOVER EM PRODUÇÃO):
            #server = self.server
            #username = self.username
            #password = self.password
            
            return server, username, password, database
        except Exception as e:
            raise Exception(f"Erro ao descriptografar credenciais: {str(e)}")
    
    def get_connection_string(self):
        """Gerar string de conexão"""
        server, username, password, database = self.decrypt_credentials()
        
        connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )
        
        return connection_string
    
    def get_connection(self):
        """Obter conexão com o banco de dados"""
        try:
            connection_string = self.get_connection_string()
            conn = pyodbc.connect(connection_string)
            return conn
        except pyodbc.Error as e:
            raise Exception(f"Erro ao conectar com o banco de dados: {str(e)}")
        except Exception as e:
            raise Exception(f"Erro geral: {str(e)}")
    
    def test_connection(self):
        """Testar conexão com o banco"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            conn.close()
            return True, "Conexão estabelecida com sucesso!"
        except Exception as e:
            return False, f"Erro na conexão: {str(e)}"

# Função utilitária para criptografar credenciais
def generate_encrypted_credentials():
    """
    Execute este script uma vez para gerar suas credenciais criptografadas
    """
    key = Fernet.generate_key()
    print(f"Chave gerada: {key}")
    
    cipher = Fernet(key)
    
    # Suas credenciais
    server = "192.169.0.1"
    username = "Marcos"
    password = "1234"
    
    # Criptografar
    encrypted_server = cipher.encrypt(server.encode())
    encrypted_username = cipher.encrypt(username.encode())
    encrypted_password = cipher.encrypt(password.encode())
    
    print("\nCredenciais criptografadas:")
    print(f"encrypted_server = {encrypted_server}")
    print(f"encrypted_username = {encrypted_username}")
    print(f"encrypted_password = {encrypted_password}")

if __name__ == "__main__":
    # Descomente para gerar credenciais criptografadas
    # generate_encrypted_credentials()
    
    # Testar conexão
    db = DatabaseManager()
    success, message = db.test_connection()
    print(f"Teste de conexão: {message}")