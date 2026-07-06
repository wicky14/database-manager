import base64
import getpass
import hashlib
import hmac
import os
import socket
import struct
import uuid
from pathlib import Path


ENCRYPTED_PREFIX = "!ENC:"


def _get_machine_secret() -> bytes:
    machine = socket.gethostname().encode()
    for source in [
        lambda: Path("/etc/machine-id").read_bytes().strip(),
        lambda: Path("/var/lib/dbus/machine-id").read_bytes().strip(),
        lambda: uuid.UUID(int=uuid.getnode()).hex.encode(),
    ]:
        try:
            machine = source()
            break
        except Exception:
            continue
    user = getpass.getuser().encode()
    return machine + b":" + user


def _derive_key(master: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master, salt, 100000, dklen=32)


def _keystream(key: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, struct.pack(">I", counter), "sha256").digest()
        counter += 1
    return out[:length]


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    master = _get_machine_secret()
    salt = os.urandom(16)
    key = _derive_key(master, salt)
    data = plaintext.encode("utf-8")
    ks = _keystream(key, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, ks))
    return ENCRYPTED_PREFIX + base64.b64encode(salt + ciphertext).decode("ascii")


def decrypt(ciphertext_b64: str) -> str:
    if not ciphertext_b64:
        return ""
    if not ciphertext_b64.startswith(ENCRYPTED_PREFIX):
        return ciphertext_b64
    try:
        raw = base64.b64decode(ciphertext_b64[len(ENCRYPTED_PREFIX):])
        if len(raw) < 16:
            return ""
        salt, ciphertext = raw[:16], raw[16:]
        master = _get_machine_secret()
        key = _derive_key(master, salt)
        ks = _keystream(key, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
        return plaintext.decode("utf-8")
    except Exception:
        return ""
