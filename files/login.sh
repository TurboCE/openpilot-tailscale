#!/usr/bin/env bash
set -eu
if (( EUID != 0 )); then
  exec sudo -n /usr/bin/bash "$0" "$@"
fi
host_name=${1:-$(hostname)}
# Ordinary OpenSSH stays in use. Do not change DNS or accept subnet routes.
exec /data/tailscale/bin/tailscale --socket=/run/tailscale/tailscaled.sock up --accept-dns=false --accept-routes=false --hostname="$host_name" --timeout=30s
