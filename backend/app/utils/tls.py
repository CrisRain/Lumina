import os
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _build_subject_alt_names(common_name: str):
    names = [
        x509.DNSName("localhost"),
        x509.IPAddress(ip_address("127.0.0.1")),
    ]

    if common_name and common_name != "localhost":
        try:
            names.append(x509.IPAddress(ip_address(common_name)))
        except ValueError:
            names.append(x509.DNSName(common_name))

    return x509.SubjectAlternativeName(names)


def ensure_self_signed_certificate(cert_path: str, key_path: str, common_name: str = "localhost") -> bool:
    """
    Ensure cert/key files exist. Generate a fresh self-signed pair if one is missing.
    Returns True when a new certificate pair is generated, otherwise False.
    """
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return False

    cert_dir = os.path.dirname(cert_path) or "."
    key_dir = os.path.dirname(key_path) or "."
    os.makedirs(cert_dir, exist_ok=True)
    os.makedirs(key_dir, exist_ok=True)

    cn = (common_name or "localhost").strip() or "localhost"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(_build_subject_alt_names(cn), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    with open(key_path, "wb") as key_file:
        key_file.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_path, "wb") as cert_file:
        cert_file.write(cert.public_bytes(serialization.Encoding.PEM))

    try:
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
    except OSError:
        pass

    return True
