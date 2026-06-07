from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security import generate_ed25519_keypair, public_key_id
from security.encoding import b64encode

CERT_DIR = Path("db/certs")
POSTGRES_HOST = "db"
DEFAULT_DAYS = 3650
CA_COMMON_NAME = "SICC Local Database CA"


def cmd_secret() -> None:
    print(f"SICC_AGENT_ENROLLMENT_SECRET={secrets.token_urlsafe(32)}")


def cmd_keypair() -> None:
    keypair = generate_ed25519_keypair()
    key_id = public_key_id(keypair.public_key)
    print(f"SICC_SERVICE_KEY_ID={key_id}")
    print(f"SICC_SERVICE_PRIVATE_KEY_B64={b64encode(keypair.private_key)}")
    print(f"SICC_SERVICE_PUBLIC_KEY_B64={b64encode(keypair.public_key)}")


def refuse_overwrite(paths: list[Path], cert_dir: Path) -> None:
    existing = [path for path in paths if path.exists()]
    if existing:
        files = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Refusing to overwrite existing cert files in {cert_dir}: {files}\n"
            "Remove the existing files first if you want to rotate the database "
            "TLS certificates."
        )


def private_key(bits: int) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def subject(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def san_for_host(host: str) -> x509.SubjectAlternativeName:
    try:
        return x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))])
    except ValueError:
        return x509.SubjectAlternativeName([x509.DNSName(host)])


def write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, 0o600)

    # Windows-specific ACL restriction for PostgreSQL
    if os.name == "nt":
        try:
            user = getpass.getuser()
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant", f"{user}:(R,W)"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            print(
                f"Warning: Could not set strict Windows permissions on {path}. "
                f"icacls output: {exc.stderr.strip()}"
            )
        except Exception as exc:
            print(f"Warning: Failed to execute icacls on {path}: {exc}")


def write_certificate(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(path, 0o644)


def build_ca_cert(
    ca_key: rsa.RSAPrivateKey,
    days: int,
    now: datetime,
) -> x509.Certificate:
    name = subject(CA_COMMON_NAME)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )


def build_server_cert(
    server_key: rsa.RSAPrivateKey,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    postgres_host: str,
    days: int,
    now: datetime,
) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(subject(postgres_host))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(san_for_host(postgres_host), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )


def cmd_db_certs(days: int) -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    ca_key_path = CERT_DIR / "ca.key"
    ca_crt_path = CERT_DIR / "ca.crt"
    server_key_path = CERT_DIR / "server.key"
    server_crt_path = CERT_DIR / "server.crt"

    refuse_overwrite(
        [ca_key_path, ca_crt_path, server_key_path, server_crt_path],
        CERT_DIR,
    )

    now = datetime.now(UTC)
    ca_key = private_key(4096)
    server_key = private_key(2048)
    ca_cert = build_ca_cert(ca_key, days, now)
    server_cert = build_server_cert(
        server_key,
        ca_key,
        ca_cert,
        POSTGRES_HOST,
        days,
        now,
    )

    write_private_key(ca_key_path, ca_key)
    write_certificate(ca_crt_path, ca_cert)
    write_private_key(server_key_path, server_key)
    write_certificate(server_crt_path, server_cert)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SICC secrets and keypairs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("secret", help="Generate a random enrollment secret token")
    subparsers.add_parser("keypair", help="Generate an Ed25519 keypair for the service")
    certparser = subparsers.add_parser(
        "db-certs", help="Generate database certificates"
    )
    certparser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Number of days the certificate is valid for",
    )

    args = parser.parse_args()

    if args.command == "secret":
        cmd_secret()
    elif args.command == "keypair":
        cmd_keypair()
    elif args.command == "db-certs":
        if args.days <= 0:
            parser.error("--days must be greater than 0")
        cmd_db_certs(args.days)


if __name__ == "__main__":
    main()
