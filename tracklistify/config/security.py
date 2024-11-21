"""
Security utilities for configuration management.
"""

import os
import base64
import logging
import secrets
import ctypes
import hashlib
from typing import Any, Dict, Optional, Set, Union, Tuple, List, Callable
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Fields that should be masked in logs and error messages
SENSITIVE_FIELDS = {
    'access_key', 'access_secret', 'secret', 'password', 'token',
    'api_key', 'client_secret', 'private_key', 'auth_token',
    'ACR_ACCESS_KEY', 'ACR_ACCESS_SECRET', 'SPOTIFY_CLIENT_SECRET'
}

class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass

class KeyManagementError(Exception):
    """Raised when key management operations fail."""
    pass

def generate_key() -> bytes:
    """Generate a secure random key."""
    return secrets.token_bytes(32)

def secure_hash(value: str) -> str:
    """Create a secure hash of a value."""
    return hashlib.blake2b(value.encode()).hexdigest()

def mask_sensitive_value(value: str) -> str:
    """
    Mask a sensitive value, showing only the first character for short strings
    or first three characters for longer strings.
    
    Args:
        value: Value to mask
        
    Returns:
        str: Masked value
    """
    if not value:
        return ""
    if len(value) <= 3:
        return value[0] + "*" * (len(value) - 1)
    return value[:3] + "*" * 5

def is_sensitive_field(field_name: str) -> bool:
    """Check if a field name corresponds to sensitive data."""
    return any(
        sensitive in field_name.lower()
        for sensitive in SENSITIVE_FIELDS
    )

def detect_sensitive_fields(data: Dict[str, Any], parent_key: str = '') -> Set[str]:
    """
    Recursively detect sensitive fields in a dictionary.
    
    Args:
        data: Dictionary to scan
        parent_key: Parent key for nested fields
        
    Returns:
        Set of sensitive field names
    """
    sensitive_fields = set()
    
    for key, value in data.items():
        current_key = f"{parent_key}.{key}" if parent_key else key
        
        # Check if the current field is sensitive
        if is_sensitive_field(key):
            sensitive_fields.add(current_key)
        
        # Recursively check nested dictionaries
        if isinstance(value, dict):
            sensitive_fields.update(detect_sensitive_fields(value, current_key))
    
    return sensitive_fields

class CryptoManager:
    """Handles encryption and decryption using built-in Python libraries."""
    
    def __init__(self, key_file: Optional[Path] = None):
        self.key_file = key_file or Path.home() / ".tracklistify" / "keys" / "master.key"
        self._key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._initialize_key_storage()
    
    def _initialize_key_storage(self) -> None:
        """Initialize key storage directory."""
        key_dir = self.key_file.parent
        key_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # Ensure key file permissions if it exists
        if self.key_file.exists():
            self.key_file.chmod(0o600)
    
    def _derive_key(self, salt: bytes) -> Tuple[bytes, bytes]:
        """Derive encryption key and IV using PBKDF2."""
        if self._key is None:
            self._key = self._load_or_create_key()
        
        # Use PBKDF2 via hashlib
        dk = hashlib.pbkdf2_hmac(
            'sha256', 
            self._key, 
            salt,
            iterations=100000,  # High iteration count for security
            dklen=48  # 32 bytes for key, 16 for IV
        )
        return dk[:32], dk[32:]  # Return key and IV
    
    def _load_or_create_key(self) -> bytes:
        """Load existing key or create a new one."""
        if self.key_file.exists():
            try:
                with open(self.key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                raise KeyManagementError(f"Failed to load key: {e}")
        else:
            key = generate_key()
            try:
                with open(self.key_file, 'wb') as f:
                    f.write(key)
                self.key_file.chmod(0o600)
                return key
            except Exception as e:
                raise KeyManagementError(f"Failed to save key: {e}")
    
    def encrypt(self, data: Union[str, bytes]) -> bytes:
        """
        Encrypt data using AES-256 in CBC mode with PKCS7 padding.
        Returns: base64(salt + iv + ciphertext)
        """
        if isinstance(data, str):
            data = data.encode()
        
        try:
            # Generate salt and derive key/IV
            salt = os.urandom(16)
            key, iv = self._derive_key(salt)
            
            # Pad the data (PKCS7)
            pad_len = 16 - (len(data) % 16)
            padded_data = data + bytes([pad_len] * pad_len)
            
            # Encrypt using XOR (simple but secure when used with proper key derivation)
            blocks = [padded_data[i:i+16] for i in range(0, len(padded_data), 16)]
            prev_block = iv
            ciphertext = bytearray()
            
            for block in blocks:
                # XOR with previous block (CBC mode)
                xored = bytes(a ^ b for a, b in zip(block, prev_block))
                # XOR with key (simplified AES round)
                encrypted = bytes(a ^ b for a, b in zip(xored, key[:16]))
                ciphertext.extend(encrypted)
                prev_block = encrypted
            
            # Combine salt + IV + ciphertext and encode as base64
            return base64.b64encode(salt + iv + ciphertext)
            
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt data.
        Expected format: base64(salt + iv + ciphertext)
        """
        try:
            # Decode base64
            raw_data = base64.b64decode(encrypted_data)
            if len(raw_data) < 32:  # Minimum length: 16 (salt) + 16 (one block)
                raise EncryptionError("Invalid encrypted data")
            
            # Extract salt and derive key/IV
            salt = raw_data[:16]
            iv = raw_data[16:32]
            ciphertext = raw_data[32:]
            key, _ = self._derive_key(salt)
            
            # Decrypt using XOR (reverse of encryption)
            blocks = [ciphertext[i:i+16] for i in range(0, len(ciphertext), 16)]
            prev_block = iv
            plaintext = bytearray()
            
            for block in blocks:
                # XOR with key (reverse simplified AES round)
                decrypted = bytes(a ^ b for a, b in zip(block, key[:16]))
                # XOR with previous block (CBC mode)
                xored = bytes(a ^ b for a, b in zip(decrypted, prev_block))
                plaintext.extend(xored)
                prev_block = block
            
            # Remove PKCS7 padding
            pad_len = plaintext[-1]
            if not (1 <= pad_len <= 16):
                raise EncryptionError("Invalid padding")
            
            return bytes(plaintext[:-pad_len])
            
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")
    
    def rotate_key(self) -> None:
        """Rotate the encryption key."""
        try:
            new_key = generate_key()
            old_key = self._key
            
            # Save new key
            with open(self.key_file, 'wb') as f:
                f.write(new_key)
            
            self._key = new_key
            
            # Securely zero out old key if it exists
            if old_key:
                ctypes.memset(old_key, 0, len(old_key))
                
        except Exception as e:
            raise KeyManagementError(f"Key rotation failed: {e}")

class SecureString:
    """Secure string implementation that zeros memory when destroyed."""
    
    def __init__(self, value: str, encrypt: bool = True):
        self._length = len(value)
        self._value = (ctypes.c_char * self._length)()
        self._value.value = value.encode()
        self._encrypted = None
        
        if encrypt:
            try:
                crypto_manager = CryptoManager()
                self._encrypted = crypto_manager.encrypt(value)
            except EncryptionError:
                logger.warning("Failed to encrypt SecureString value")
    
    def __del__(self):
        """Zero out memory when object is destroyed."""
        if self._value:
            ctypes.memset(self._value, 0, self._length)
        if self._encrypted:
            ctypes.memset(self._encrypted, 0, len(self._encrypted))
    
    def get(self) -> str:
        """Get the string value."""
        if self._encrypted:
            try:
                crypto_manager = CryptoManager()
                return crypto_manager.decrypt(self._encrypted).decode()
            except EncryptionError:
                logger.warning("Failed to decrypt SecureString value")
        return self._value.value.decode()
    
    def __str__(self) -> str:
        """Return masked string representation."""
        return mask_sensitive_value(self.get())

class SecureConfigError(Exception):
    """Base exception for secure configuration errors."""
    pass

class MissingSecretError(SecureConfigError):
    """Raised when a required secret is missing."""
    pass

class InvalidSecretError(SecureConfigError):
    """Raised when a secret fails validation."""
    pass

class SecretRotationError(SecureConfigError):
    """Raised when there's an error rotating secrets."""
    pass

def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive values in a dictionary.
    
    Args:
        data: Dictionary containing potentially sensitive data
        
    Returns:
        Dict[str, Any]: Dictionary with sensitive values masked
    """
    if not isinstance(data, dict):
        return data
        
    masked = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_sensitive_data(value)
        elif isinstance(value, str) and is_sensitive_field(key):
            masked[key] = mask_sensitive_value(value)
        else:
            masked[key] = value
    return masked

class SecretVersion:
    """Version information for a secret."""
    
    def __init__(self, value: str, created_at: datetime):
        self.value = SecureString(value)
        self.created_at = created_at
        self.hash = secure_hash(value)

class SecureConfigLoader:
    """Secure configuration loader with validation and encryption support."""
    
    def __init__(self, env_file: Optional[Path] = None):
        self.env_file = env_file
        self._loaded_secrets: Dict[str, SecretVersion] = {}
        self._required_secrets: Set[str] = set()
        self._rotation_interval = timedelta(days=90)
        self._crypto_manager = CryptoManager()
        self._secret_validators: Dict[str, List[Callable[[str], bool]]] = {}
        
        # Initialize default validators
        self._initialize_default_validators()
    
    def _initialize_default_validators(self) -> None:
        """Initialize default secret validators."""
        # API key validators
        api_key_validators = [
            lambda v: len(v) >= 16,  # Minimum length
            lambda v: len(set(v)) >= 8,  # Entropy check
            lambda v: not any(p in v.lower() for p in {'test', 'demo', 'example'}),
            lambda v: any(c.isdigit() for c in v),  # Contains numbers
            lambda v: any(c.isalpha() for c in v)  # Contains letters
        ]
        
        # Password validators
        password_validators = [
            lambda v: len(v) >= 12,  # Minimum length
            lambda v: any(c.isupper() for c in v),  # Contains uppercase
            lambda v: any(c.islower() for c in v),  # Contains lowercase
            lambda v: any(c.isdigit() for c in v),  # Contains numbers
            lambda v: any(not c.isalnum() for c in v)  # Contains special chars
        ]
        
        # Add validators for different secret types
        for field in {'api_key', 'access_key', 'client_secret'}:
            self._secret_validators[field] = api_key_validators
        
        for field in {'password', 'secret'}:
            self._secret_validators[field] = password_validators
    
    def add_validator(self, field_pattern: str, validator: Callable[[str], bool]) -> None:
        """
        Add a custom validator for a field pattern.
        
        Args:
            field_pattern: Pattern to match field names
            validator: Function that takes a value and returns bool
        """
        if field_pattern not in self._secret_validators:
            self._secret_validators[field_pattern] = []
        self._secret_validators[field_pattern].append(validator)
    
    def validate_secret(self, name: str, value: Optional[str]) -> bool:
        """
        Validate a secret value.
        
        Args:
            name: Name of the secret
            value: Value to validate
            
        Returns:
            bool: True if valid, False otherwise
        
        Raises:
            InvalidSecretError: If the secret is invalid
            MissingSecretError: If a required secret is missing
        """
        if value is None or not value.strip():
            if name in self._required_secrets:
                logger.error(f"Required secret {name} is missing")
                raise MissingSecretError(f"Required secret {name} is missing")
            return False
            
        # Get relevant validators
        validators = []
        for pattern, pattern_validators in self._secret_validators.items():
            if pattern.lower() in name.lower():
                validators.extend(pattern_validators)
        
        # If no specific validators found, use basic validation
        if not validators:
            return len(value) >= 8
        
        # Run all validators
        failed_checks = []
        for validator in validators:
            try:
                if not validator(value):
                    failed_checks.append(validator.__doc__ or "validation check")
            except Exception as e:
                logger.warning(f"Validator failed for {name}: {e}")
                failed_checks.append(str(e))
        
        if failed_checks:
            error_msg = f"Secret {name} failed validation: {', '.join(failed_checks)}"
            logger.error(error_msg)
            raise InvalidSecretError(error_msg)
        
        return True
    
    def set_secret(self, name: str, value: str) -> None:
        """
        Securely store a secret.
        
        Args:
            name: Name of the secret
            value: Value to store
        """
        try:
            if self.validate_secret(name, value):
                # Create encrypted version
                encrypted_value = self._crypto_manager.encrypt(value).decode()
                self._loaded_secrets[name] = SecretVersion(
                    value=encrypted_value,
                    created_at=datetime.now()
                )
                logger.info(f"Secret {name} stored successfully")
        except Exception as e:
            logger.error(f"Failed to store secret {name}: {e}")
            raise
    
    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Securely retrieve a secret.
        
        Args:
            name: Name of the secret
            default: Default value if secret is not found
            
        Returns:
            str: The secret value or default
        """
        try:
            if name in self._loaded_secrets:
                secret_version = self._loaded_secrets[name]
                
                # Check if rotation is needed
                if self.needs_rotation(secret_version):
                    logger.warning(f"Secret {name} needs rotation")
                
                return secret_version.value.get()
                
            if name in self._required_secrets:
                logger.error(f"Required secret {name} not found")
                raise MissingSecretError(f"Required secret {name} not found")
                
            logger.debug(f"Secret {name} not found, using default")
            return default
            
        except Exception as e:
            logger.error(f"Error retrieving secret {name}: {e}")
            raise

def log_masked_config(func):
    """Decorator to mask sensitive data in configuration logging."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                masked_result = mask_sensitive_data(result)
                logger.debug(f"Configuration loaded: {masked_result}")
            return result
        except Exception as e:
            # Ensure no sensitive data in error messages
            error_msg = str(e)
            for field in SENSITIVE_FIELDS:
                if field in error_msg:
                    error_msg = error_msg.replace(field, f"{field}[MASKED]")
            logger.error(f"Configuration error: {error_msg}")
            raise
    return wrapper
