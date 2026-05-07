param(
    [string]$CertDir = "db/certs",
    [string]$PostgresHost = "db",
    [int]$Days = 3650
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

$caKey = Join-Path $CertDir "ca.key"
$caCrt = Join-Path $CertDir "ca.crt"
$serverKey = Join-Path $CertDir "server.key"
$serverCsr = Join-Path $CertDir "server.csr"
$serverCrt = Join-Path $CertDir "server.crt"
$serverExt = Join-Path $CertDir "server.ext"

$existing = @($caKey, $caCrt, $serverKey, $serverCrt) | Where-Object { Test-Path $_ }
if ($existing.Count -gt 0) {
    Write-Error "Refusing to overwrite existing cert files in $CertDir. Remove them first if you want to rotate the database TLS certificates."
}

openssl genrsa -out $caKey 4096
openssl req -x509 -new -nodes -key $caKey -sha256 -days $Days `
    -subj "/CN=SICC Local Database CA" `
    -out $caCrt

openssl genrsa -out $serverKey 2048
openssl req -new -key $serverKey `
    -subj "/CN=$PostgresHost" `
    -out $serverCsr

@"
subjectAltName = DNS:$PostgresHost
extendedKeyUsage = serverAuth
keyUsage = digitalSignature, keyEncipherment
"@ | Set-Content -NoNewline -Path $serverExt

openssl x509 -req -in $serverCsr `
    -CA $caCrt -CAkey $caKey -CAcreateserial `
    -out $serverCrt -days $Days -sha256 `
    -extfile $serverExt

Remove-Item -Path $serverCsr, $serverExt -Force

$caSrl = Join-Path $CertDir "ca.srl"
if (Test-Path $caSrl) { Remove-Item -Path $caSrl -Force }

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls $caKey /inheritance:r /grant "${currentUser}:(R,W)" | Out-Null
icacls $serverKey /inheritance:r /grant "${currentUser}:(R,W)" | Out-Null

Write-Host "Generated database TLS certificates in $CertDir"
Write-Host "Postgres certificate is valid for DNS:$PostgresHost"
