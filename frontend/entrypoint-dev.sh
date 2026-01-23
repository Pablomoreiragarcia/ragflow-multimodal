#!/bin/sh
set -e

mkdir -p /app/node_modules /app/.next
chown -R node:node /app/node_modules /app/.next || true

# (Opcional) instala deps si aún no existen
if [ ! -f /app/node_modules/.package-lock.json ] && [ ! -d /app/node_modules/react ]; then
  su -s /bin/sh node -c "npm install"
fi

exec su -s /bin/sh node -c "$*"
