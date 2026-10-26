#!/bin/sh
set -eu
# NET_ADMIN is used only in this NEW container namespace, never on the host.
# The published ingress uses its connected subnet; no default egress route remains.
while [ -n "$(ip route | sed -n '/^default /p')" ]; do
    ip route del default
done
[ -z "$(ip route | sed -n '/^default /p')" ] || exit 1
cp /run/secrets/server_key /tmp/server.key
cp /run/secrets/server_cert /tmp/server.crt
chmod 600 /tmp/server.key /tmp/server.crt
chown 101:101 /tmp/server.key /tmp/server.crt
# setuid drops effective/permitted capabilities; no-new-privileges prevents regain.
exec su nginx -s /bin/sh -c 'exec /bin/sh /opt/woo-lab/tls-unprivileged.sh'
