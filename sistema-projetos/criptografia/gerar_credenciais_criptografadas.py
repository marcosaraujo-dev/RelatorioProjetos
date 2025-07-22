"""
Script para gerar credenciais criptografadas do banco de dados
Execute APENAS UMA VEZ para gerar as credenciais criptografadas
"""

from cryptography.fernet import Fernet

def main():
    print("🔐 Gerador de Credenciais Criptografadas")
    print("=" * 50)
    
    # Gerar uma nova chave
    key = Fernet.generate_key()
    cipher = Fernet(key)
    
    print(f"Chave gerada: {key.decode()}")
    print("\n⚠️  IMPORTANTE: Guarde esta chave com segurança!")
    print("   Ela será necessária para descriptografar as credenciais.\n")
    
    # Suas credenciais (substitua pelos valores reais)
    server = "192.168.0.1"
    username = "marcos.araujo"
    password = "243545"
    database = "ProjetosDB"
    
    # Criptografar as credenciais
    encrypted_server = cipher.encrypt(server.encode())
    encrypted_username = cipher.encrypt(username.encode())
    encrypted_password = cipher.encrypt(password.encode())
    encrypted_database = cipher.encrypt(database.encode())
    
    print("📝 Credenciais criptografadas:")
    print("-" * 30)
    print(f"Chave: {key}")
    print(f"Server: {encrypted_server}")
    print(f"Username: {encrypted_username}")
    print(f"Password: {encrypted_password}")
    print(f"Database: {encrypted_database}")
    
    print("\n📋 Código para usar no database.py:")
    print("-" * 40)
    
    code_template = f"""
class DatabaseManager:
    def __init__(self):
        # Chave de criptografia (mantenha segura!)
        key = {key}
        self.cipher = Fernet(key)
        
        # Credenciais criptografadas
        self.encrypted_server = {encrypted_server}
        self.encrypted_username = {encrypted_username}
        self.encrypted_password = {encrypted_password}
        self.encrypted_database = {encrypted_database}
    
    def decrypt_credentials(self):
        try:
            server = self.cipher.decrypt(self.encrypted_server).decode()
            username = self.cipher.decrypt(self.encrypted_username).decode()
            password = self.cipher.decrypt(self.encrypted_password).decode()
            database = self.cipher.decrypt(self.encrypted_database).decode()
            return server, username, password, database
        except Exception as e:
            raise Exception(f"Erro ao descriptografar credenciais: {{str(e)}}")
"""
    
    print(code_template)
    
    # Salvar em arquivo
    with open("credenciais_criptografadas.txt", "w") as f:
        f.write("CREDENCIAIS CRIPTOGRAFADAS\n")
        f.write("=" * 30 + "\n\n")
        f.write(f"Chave: {key.decode()}\n")
        f.write(f"Server: {encrypted_server}\n")
        f.write(f"Username: {encrypted_username}\n")
        f.write(f"Password: {encrypted_password}\n")
        f.write(f"Database: {encrypted_database}\n\n")
        f.write("CÓDIGO PARA DATABASE.PY:\n")
        f.write("-" * 25 + "\n")
        f.write(code_template)
    
    print(f"✅ Credenciais salvas em: credenciais_criptografadas.txt")
    
    # Testar descriptografia
    print("\n🧪 Testando descriptografia...")
    try:
        decrypted_server = cipher.decrypt(encrypted_server).decode()
        decrypted_username = cipher.decrypt(encrypted_username).decode()
        decrypted_password = cipher.decrypt(encrypted_password).decode()
        decrypted_database = cipher.decrypt(encrypted_database).decode()
        
        print("✅ Teste de descriptografia bem-sucedido!")
        print(f"   Server: {decrypted_server}")
        print(f"   Username: {decrypted_username}")
        print(f"   Password: {'*' * len(decrypted_password)}")
        print(f"   Database: {decrypted_database}")
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
    
    print("\n" + "=" * 50)
    print("🔒 Agora você pode:")
    print("1. Copiar o código gerado para database.py")
    print("2. Remover as credenciais em texto claro")
    print("3. Deletar este script e o arquivo .txt por segurança")
    print("\n⚠️  NUNCA compartilhe a chave de criptografia!")

if __name__ == "__main__":
    main()
    input("\nPressione Enter para sair...")