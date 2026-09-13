# app/services/signing.py

import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature


class SigningService:
    @staticmethod
    def generate_keypair() -> tuple[str, str]:
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        priv_bytes = private_key.private_bytes_raw()
        pub_bytes = public_key.public_bytes_raw()
        return base64.b64encode(priv_bytes).decode(), base64.b64encode(pub_bytes).decode()

    @staticmethod
    def sign_content(private_key_b64: str, content: bytes) -> str:
        priv_bytes = base64.b64decode(private_key_b64)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        signature = private_key.sign(content)
        return base64.b64encode(signature).decode()

    @staticmethod
    def verify_signature(public_key_b64: str, content: bytes, signature_b64: str) -> bool:
        try:
            pub_bytes = base64.b64decode(public_key_b64)
            sig_bytes = base64.b64decode(signature_b64)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, content)
            return True
        except (InvalidSignature, ValueError):
            return False