#!/usr/bin/env bash
# Run on the OVH Ubuntu VM from the project root.
set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v docker >/dev/null 2>&1; then
  echo "[ovh] installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "${USER}"
fi

if [[ ! -f .env.production ]]; then
  echo "[ovh] creating .env.production from the example"
  cp deploy/ovh/env.production.example .env.production
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  PG_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  NEO_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env.production
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|" .env.production
  sed -i "s|^NEO4J_PASSWORD=.*|NEO4J_PASSWORD=${NEO_PASS}|" .env.production
  PUBLIC_IP="$(curl -fsS https://ipv4.icanhazip.com || true)"
  if [[ -n "${PUBLIC_IP}" ]]; then
    sed -i "s|http://YOUR_OVH_IP|http://${PUBLIC_IP}|" .env.production
    echo "[ovh] public IP ${PUBLIC_IP} written to BACKEND_CORS_ORIGINS"
  fi
fi

if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow OpenSSH || true
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
  sudo ufw --force enable || true
fi

echo "[ovh] building and starting the stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build

echo
echo "[ovh] waiting for API health..."
for _ in $(seq 1 60); do
  if docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null; then
    echo "[ovh] backend is healthy"
    break
  fi
  sleep 5
done

PUBLIC_IP="$(curl -fsS https://ipv4.icanhazip.com || echo 'YOUR_OVH_IP')"
echo
echo "App URL:  http://${PUBLIC_IP}"
echo "Health:   http://${PUBLIC_IP}/api/health"
echo "Login:    value of FIRST_SUPERUSER_EMAIL in .env.production"
echo
echo "Add a domain later: set SITE_ADDRESS=skills.yourdomain.com and ACME_EMAIL in .env.production,"
echo "point the DNS A record at ${PUBLIC_IP}, then: docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d caddy"
