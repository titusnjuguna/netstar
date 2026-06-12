#!/bin/bash
# One-time bootstrap for the Let's Encrypt certificate used by nginx.conf.
# Run this once on the host before "docker-compose up -d":
#   chmod +x init-letsencrypt.sh && ./init-letsencrypt.sh
set -e

domain=api.net.babybull.cc
email=titusnjuguna59@gmail.com  

data_path="./certbot"
rsa_key_size=4096

if [ -d "$data_path/conf/live/$domain" ]; then
  echo "Existing certificate data found for $domain, skipping bootstrap."
  exit 0
fi

echo "### Creating dummy certificate for $domain ..."
mkdir -p "$data_path/conf/live/$domain"
docker compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1 \
    -keyout '/etc/letsencrypt/live/$domain/privkey.pem' \
    -out '/etc/letsencrypt/live/$domain/fullchain.pem' \
    -subj '/CN=localhost'" certbot

echo "### Starting nginx ..."
docker compose up -d nginx

echo "### Deleting dummy certificate for $domain ..."
docker compose run --rm --entrypoint "\
  rm -rf /etc/letsencrypt/live/$domain && \
  rm -rf /etc/letsencrypt/archive/$domain && \
  rm -rf /etc/letsencrypt/renewal/$domain.conf" certbot

echo "### Requesting real certificate for $domain ..."
docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    --email $email -d $domain \
    --rsa-key-size $rsa_key_size --agree-tos --no-eff-email" certbot

echo "### Reloading nginx ..."
docker compose exec nginx nginx -s reload
