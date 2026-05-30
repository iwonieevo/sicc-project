class CryptoError(Exception):
    """Base exception for SICC secure transport failures."""


class DecodeError(CryptoError):
    """Raised when an encoded envelope or key has invalid shape."""


class DecryptionError(CryptoError):
    """Raised when authenticated decryption fails."""


class ReplayError(CryptoError):
    """Raised when a message sequence number is not the expected next value."""


class SignatureVerificationError(CryptoError):
    """Raised when Ed25519 transcript verification fails."""


class StaleMessageError(CryptoError):
    """Raised when a decrypted message timestamp is outside the allowed skew."""
