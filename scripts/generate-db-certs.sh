#!/bin/sh
set -eu

CERT_DIR="${CERT_DIR:-db/certs}"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
DAYS="${CERT_DAYS:-3650}"

mkdir -p "$CERT_DIR"

CA_KEY="$CERT_DIR/ca.key"
CA_CRT="$CERT_DIR/ca.crt"
SERVER_KEY="$CERT_DIR/server.key"
SERVER_CSR="$CERT_DIR/server.csr"
SERVER_CRT="$CERT_DIR/server.crt"
SERVER_EXT="$CERT_DIR/server.ext"

if [ -e "$CA_KEY" ] || [ -e "$CA_CRT" ] || [ -e "$SERVER_KEY" ] || [ -e "$SERVER_CRT" ]; then
  echo "Refusing to overwrite existing cert files in $CERT_DIR"
  echo "Remove the existing files first if you want to rotate the database TLS certificates."
  exit 1
fi

openssl genrsa -out "$CA_KEY" 4096
openssl req -x509 -new -nodes -key "$CA_KEY" -sha256 -days "$DAYS" \
  -subj "/CN=SICC Local Database CA" \
  -out "$CA_CRT"

openssl genrsa -out "$SERVER_KEY" 2048
openssl req -new -key "$SERVER_KEY" \
  -subj "/CN=$POSTGRES_HOST" \
  -out "$SERVER_CSR"

cat > "$SERVER_EXT" <<EOF
subjectAltName = DNS:$POSTGRES_HOST
extendedKeyUsage = serverAuth
keyUsage = digitalSignature, keyEncipherment
EOF

openssl x509 -req -in "$SERVER_CSR" \
  -CA "$CA_CRT" -CAkey "$CA_KEY" -CAcreateserial \
  -out "$SERVER_CRT" -days "$DAYS" -sha256 \
  -extfile "$SERVER_EXT"

chmod 600 "$CA_KEY" "$SERVER_KEY"
chmod 644 "$CA_CRT" "$SERVER_CRT"

rm -f "$SERVER_CSR" "$SERVER_EXT" "$CERT_DIR/ca.srl"

echo "Generated database TLS certificates in $CERT_DIR"
echo "Postgres certificate is valid for DNS:$POSTGRES_HOST"
