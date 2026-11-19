#!/usr/bin/env bash
# The server's edge firewall (Hetzner Robot): stateless, in front of the host's own (host/nftables.conf).
# Admits replies to the server's own connections, Tailscale, and HTTPS from ENTSO-E's push addresses only.
# SSH and everything else arrive over the tailnet.
#
#   ROBOT_USER=... ROBOT_PASSWORD=... SERVER_ID=... ./robot-firewall.sh
#   BREAK_GLASS_IP=<your address> ...                     # also SSH from that address, while the tailnet is down
#
# ROBOT_USER / ROBOT_PASSWORD: the Robot webservice user (Robot > Settings > Webservice), not the login.
# Hetzner's own services (rescue system, monitoring) stay admitted (whitelist_hos).
set -euo pipefail

: "${ROBOT_USER:?}" "${ROBOT_PASSWORD:?}" "${SERVER_ID:?}"
# ENTSO-E's subscription service pushes from these (services/README.md)
ENTSOE_IPS=(4.185.182.62 4.182.105.72)

rules=(status=active filter_ipv6=true whitelist_hos=true)
i=0
rule() {  # rule <name> <field=value>...
  rules+=("rules[input][$i][name]=$1")
  shift
  for field in "$@"; do rules+=("rules[input][$i][${field%%=*}]=${field#*=}"); done
  rules+=("rules[input][$i][action]=accept")
  i=$((i + 1))
}

rule "icmp" ip_version=ipv4 protocol=icmp
for v in ipv4 ipv6; do
  # stateless: replies to the server's own connections (TCP), DNS, NTP and Tailscale (UDP) on ephemeral ports
  rule "tcp replies $v" ip_version=$v protocol=tcp dst_port=32768-65535 tcp_flags=ack
  rule "udp replies, tailscale $v" ip_version=$v protocol=udp dst_port=32768-65535
done
for ip in "${ENTSOE_IPS[@]}"; do
  rule "entsoe push $ip" ip_version=ipv4 protocol=tcp src_ip="$ip/32" dst_port=443
done
if [ -n "${BREAK_GLASS_IP:-}" ]; then
  rule "ssh break-glass" ip_version=ipv4 protocol=tcp src_ip="$BREAK_GLASS_IP/32" dst_port=22
fi
rules+=("rules[output][0][name]=all" "rules[output][0][action]=accept")

args=()
for r in "${rules[@]}"; do args+=(--data-urlencode "$r"); done
# credentials on stdin, not the command line
printf 'user = "%s:%s"\n' "$ROBOT_USER" "$ROBOT_PASSWORD" |
  curl --fail-with-body -sS -K - "https://robot-ws.your-server.de/firewall/$SERVER_ID" "${args[@]}" |
  jq '.firewall | {status, filter_ipv6, input: [.rules.input[] | .name]}'
