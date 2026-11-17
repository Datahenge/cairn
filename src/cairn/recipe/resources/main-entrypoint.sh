#!/bin/bash
set -e

ASSETS_PATH="/home/frappe/frappe-bench/sites/assets"
BAKED_PATH="/home/frappe/frappe-bench/assets"

# The sites volume is shared by every container in the stack, and the link resolves inside
# each container to that container's own baked assets. When it already points there, leave
# it: a hot swap starts new containers while the old frontend is serving through this link,
# and removing it even briefly would 404 its asset requests (BR-VEND-001, BR-DEPLOY-025).
if [ "$(readlink "$ASSETS_PATH")" != "$BAKED_PATH" ]; then
  echo "Linking fresh assets to volume..."
  rm -rf "$ASSETS_PATH"
  mkdir -p "$(dirname "$ASSETS_PATH")"
  ln -s "$BAKED_PATH" "$ASSETS_PATH"
fi

exec "$@"
