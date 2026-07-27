"""Generate self-signed dev certificates for mTLS using Python cryptography."""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

CERT_DIR = Path(__file__).parent

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("Install cryptography: pip install cryptography")
    sys.exit(1)


SERVICES = [
    ("api", ["DNS:localhost", "DNS:api-service", "IP:127.0.0.1"]),
    ("worker", ["DNS:localhost", "DNS:worker", "IP:127.0.0.1"]),
    ("autoscaler", ["DNS:localhost", "DNS:autoscaler", "IP:127.0.0.1"]),
    ("monitor", ["DNS:localhost", "DNS:monitoring-service", "IP:127.0.0.1"]),
]


def make_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )


def make_ca():
    key = make_key()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "PlagioScale Dev CA"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1000)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            key_cert_sign=True, crl_sign=True,
            digital_signature=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False,
            content_commitment=False,
        ), critical=True)
        .sign(key, hashes.SHA256(), default_backend())
    )
    return key, cert


def make_server_cert(ca_key, ca_cert, common_name, sans):
    key = make_key()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    san_list = x509.SubjectAlternativeName([x509.DNSName(s.split(":")[1]) if s.startswith("DNS:") else x509.IPAddress(__import__("ipaddress").ip_address(s.split(":")[1])) for s in sans])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(hash(common_name) & 0xFFFFFFFF)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(san_list, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=True,
            key_cert_sign=False, crl_sign=False,
            data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False,
            content_commitment=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([
            x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
            x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
        ]), critical=False)
        .sign(ca_key, hashes.SHA256(), default_backend())
    )
    return key, cert


def write_pem(path, data, is_key=False):
    if is_key:
        pem = data.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        pem = data.public_bytes(serialization.Encoding.PEM)
    with open(path, "wb") as f:
        f.write(pem)


def main():
    print("Generating CA...")
    ca_key, ca_cert = make_ca()
    write_pem(CERT_DIR / "ca.key", ca_key, is_key=True)
    write_pem(CERT_DIR / "ca.crt", ca_cert)

    for name, sans in SERVICES:
        print(f"Generating cert for {name}...")
        key, cert = make_server_cert(ca_key, ca_cert, f"{name}-service", sans)
        write_pem(CERT_DIR / f"{name}.key", key, is_key=True)
        write_pem(CERT_DIR / f"{name}.crt", cert)

    print("Done — certs generated in certs/")
    print("\nAdd to docker-compose volumes:")
    for name, _ in SERVICES:
        print(f"  - ./certs:/app/certs:ro")

    # Also generate a combined PEM for clients that need both cert and key
    for name, _ in SERVICES:
        with open(CERT_DIR / f"{name}.combined.pem", "wb") as out:
            with open(CERT_DIR / f"{name}.crt", "rb") as f:
                out.write(f.read())
            with open(CERT_DIR / f"{name}.key", "rb") as f:
                out.write(f.read())
        print(f"  Created {name}.combined.pem")


if __name__ == "__main__":
    main()
