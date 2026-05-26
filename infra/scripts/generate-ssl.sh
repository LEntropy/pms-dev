#!/bin/bash
# 자체 서명 SSL 인증서 생성 (개발/내부망용)
# 프로덕션에서는 Let's Encrypt 또는 기업 CA 인증서를 사용하세요

set -e

SSL_DIR="$(dirname "$0")/../nginx/ssl"
mkdir -p "$SSL_DIR"

DOMAIN="${1:-pms.company.local}"

openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -subj "/CN=$DOMAIN/O=Company/C=KR" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

chmod 600 "$SSL_DIR/server.key"
echo "SSL certificate generated: $SSL_DIR/"
