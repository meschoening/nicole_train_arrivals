import os
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# WiFi credentials file
WIFI_CREDENTIALS_FILE = "wifi_credentials.enc"
# Key file for encryption
ENCRYPTION_KEY_FILE = ".wifi_key"

def _get_or_create_key():
    """Get or create encryption key"""
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        # Generate a new key
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        # Set restrictive permissions on key file
        os.chmod(ENCRYPTION_KEY_FILE, 0o600)
        return key

def _get_fernet():
    """Get Fernet instance with encryption key"""
    key = _get_or_create_key()
    return Fernet(key)

def encrypt_password(password):
    """Encrypt a password using Fernet"""
    fernet = _get_fernet()
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    """Decrypt a password using Fernet"""
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_password.encode()).decode()

def save_wifi_config(ssid, password):
    """Save WiFi credentials to encrypted file"""
    encrypted_password = encrypt_password(password)
    config = {
        "ssid": ssid,
        "password_encrypted": encrypted_password
    }
    with open(WIFI_CREDENTIALS_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    # Set restrictive permissions on credentials file
    os.chmod(WIFI_CREDENTIALS_FILE, 0o600)

def load_wifi_config():
    """Load WiFi credentials from encrypted file"""
    if not os.path.exists(WIFI_CREDENTIALS_FILE):
        return None
    try:
        with open(WIFI_CREDENTIALS_FILE, 'r') as f:
            config = json.load(f)
        # Decrypt password
        config["password"] = decrypt_password(config["password_encrypted"])
        return config
    except Exception:
        return None

