#!/usr/bin/env bash
# Background bootstrap: openpilot must not wait for network setup.
set -eu
if (( EUID != 0 )); then
  exec sudo -n /usr/bin/bash "$0" "$@"
fi
exec 9>/run/openpilot-tailscale-bootstrap.lock
flock -n 9 || exit 0
systemctl link --runtime /data/tailscale/tailscaled.service /data/tailscale/tailscaled-delay.timer
systemctl start --no-block tailscaled-delay.timer
