import os
from base64 import b64encode, b64decode
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

load_dotenv()

AES_KEY = os.getenv("AES_KEY")
if AES_KEY is None:
    print("CRITICAL: AES_KEY not found in environment. Generating a temp one.")
    AES_KEY = os.urandom(32)  # AES-256
else:
    AES_KEY = b64decode(AES_KEY)

BLOCK_SIZE = 128  # bits

def encrypt_data(data):
    if not data:
        return None

    iv = os.urandom(16)
    padder = padding.PKCS7(BLOCK_SIZE).padder()
    padded_data = padder.update(data.encode()) + padder.finalize()

    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    return b64encode(iv + ciphertext).decode()

def decrypt_data(token):
    if not token:
        return None

    raw = b64decode(token)
    iv = raw[:16]
    ciphertext = raw[16:]

    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(BLOCK_SIZE).unpadder()
    data = unpadder.update(padded_data) + unpadder.finalize()
    return data.decode()
