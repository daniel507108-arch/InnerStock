# Encrypts small secrets before they're stored in the database - currently
# each user's SnapTrade userSecret, which (together with our API keys) can
# read that user's brokerage data. If the database alone ever leaks, these
# values are useless without FIELD_ENCRYPTION_KEY, which lives only in the
# environment (Backend/.env locally, Vercel's env vars in production).
#
# Generate a key with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Changing or losing the key makes stored secrets unreadable - every user
# would have to reconnect their brokerage.
import os

from cryptography.fernet import Fernet, InvalidToken


class SecretBoxError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.getenv("FIELD_ENCRYPTION_KEY"))


def _fernet() -> Fernet:
    key = os.getenv("FIELD_ENCRYPTION_KEY")
    if not key:
        raise SecretBoxError("FIELD_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode())
    except ValueError as e:
        raise SecretBoxError("FIELD_ENCRYPTION_KEY is not a valid Fernet key") from e


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise SecretBoxError("Stored secret can't be decrypted - was FIELD_ENCRYPTION_KEY changed?") from e
