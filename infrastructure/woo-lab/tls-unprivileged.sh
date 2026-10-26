#!/bin/sh
set -eu
[ "$(id -u)" = 101 ] || exit 1
# Verify the kernel state BEFORE the service exec, not merely the username.
awk '
/^Cap(Eff|Prm|Inh|Amb):/ { seen++; if ($2 !~ /^0+$/) bad=1 }
/^NoNewPrivs:/ { seen++; if ($2 != 1) bad=1 }
END { exit (bad || seen != 5) }
' /proc/self/status
[ -z "$(ip route | sed -n '/^default /p')" ] || exit 1
exec nginx -e stderr -g 'daemon off;'
