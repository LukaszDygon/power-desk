#!/usr/bin/env bash
# Prepares a fresh server (installimage.conf) for Power Desk: security updates, the data volume, Tailscale, the
# host firewall, SSH hardening, k3s and the nightly backup. Idempotent: run it again after changing a file here.
#
#   TAILSCALE_AUTHKEY=tskey-auth-... ./bootstrap.sh     # as root on the server, from this directory
#
# The auth key: pre-approved and tagged tag:power-desk (tailnet-policy.hujson), from the admin console. Public SSH
# closes once the host firewall is up: reconnect over the tailnet (ssh root@power-desk), then close the edge
# (make firewall). Docs: docs/hosting.md.
set -euo pipefail

K3S_VERSION=${K3S_VERSION:-v1.37.2+k3s1}
TS_HOSTNAME=${TS_HOSTNAME:-power-desk}
DATA_SIZE=${DATA_SIZE:-80%FREE}  # of vg0's free space; the rest holds the backup's snapshots
HERE=$(cd "$(dirname "$0")" && pwd)

log() { printf '\n== %s\n' "$*"; }

log "packages and automatic security updates"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq --no-install-recommends ca-certificates curl jq nftables restic unattended-upgrades xfsprogs
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
timedatectl set-timezone Etc/UTC

log "data volume: XFS (reflinks), on /srv/power-desk"
if ! lvs vg0/data >/dev/null 2>&1; then
  lvcreate -y -l "$DATA_SIZE" -n data vg0
  mkfs.xfs -m reflink=1 /dev/vg0/data
fi
mkdir -p /srv/power-desk
grep -q ' /srv/power-desk ' /etc/fstab || echo '/dev/vg0/data /srv/power-desk xfs defaults,noatime 0 2' >> /etc/fstab
systemctl daemon-reload
mountpoint -q /srv/power-desk || mount /srv/power-desk
# the warehouse's directory, owned by the images' user (uid 10001), and the cluster's volumes
install -d -o 10001 -g 10001 /srv/power-desk/data /srv/power-desk/data/landing
install -d -m 0700 /srv/power-desk/volumes

log "Tailscale"
if ! command -v tailscale >/dev/null; then curl -fsSL https://tailscale.com/install.sh | sh; fi
if ! tailscale status >/dev/null 2>&1; then
  : "${TAILSCALE_AUTHKEY:?set TAILSCALE_AUTHKEY: a pre-approved auth key tagged tag:power-desk}"
  tailscale up --auth-key "$TAILSCALE_AUTHKEY" --hostname "$TS_HOSTNAME"
fi
TS_IP=$(tailscale ip -4)
TS_DNS=$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')

log "host firewall (nftables)"
PUBLIC_IF=$(ip -o route show default | awk '{print $5; exit}')
sed "s/@PUBLIC_IF@/$PUBLIC_IF/" "$HERE/nftables.conf" > /etc/nftables.conf
nft -c -f /etc/nftables.conf
systemctl enable --now nftables
nft -f /etc/nftables.conf

log "SSH: keys only"
install -m 0644 "$HERE/sshd.conf" /etc/ssh/sshd_config.d/10-power-desk.conf
sshd -t
systemctl reload ssh

log "k3s $K3S_VERSION"
install -d /etc/rancher/k3s /var/lib/rancher/k3s/server/manifests
{ cat "$HERE/k3s-config.yaml"; printf '  - %s\n  - %s\n' "$TS_IP" "$TS_DNS"; } > /etc/rancher/k3s/config.yaml
chmod 0600 /etc/rancher/k3s/config.yaml
install -m 0600 "$HERE/traefik-config.yaml" /var/lib/rancher/k3s/server/manifests/traefik-config.yaml
if [ "$(k3s --version 2>/dev/null | awk 'NR==1{print $3}')" != "$K3S_VERSION" ]; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" sh -
else
  systemctl restart k3s
fi
# k3s rewrites its own rules on start; ours live in their own table and stay

log "nightly backup (enabled once /etc/power-desk/backup.env exists: backup.env.example)"
install -m 0755 "$HERE/backup.sh" /usr/local/sbin/power-desk-backup
install -m 0644 "$HERE/power-desk-backup.service" "$HERE/power-desk-backup.timer" /etc/systemd/system/
install -d -m 0700 /etc/power-desk
systemctl daemon-reload
if [ -f /etc/power-desk/backup.env ]; then systemctl enable --now power-desk-backup.timer; fi

log "done: $TS_DNS ($TS_IP); next: make kubeconfig, then make firewall from your machine"
