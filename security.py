"""Encryption helpers for sensitive at-rest expense data."""
from cryptography.fernet import Fernet, InvalidToken


class DataCipher:
    def __init__(self, key: str):
        if not key:
            raise ValueError('ENCRYPTION_KEY is required')
        try:
            self._fernet = Fernet(key.encode('utf-8'))
        except (ValueError, TypeError) as exc:
            raise ValueError('ENCRYPTION_KEY must be a valid Fernet key') from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode('utf-8')).decode('ascii')

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode('ascii')).decode('utf-8')
        except InvalidToken as exc:
            raise ValueError('Encrypted database data cannot be decrypted with this key') from exc
