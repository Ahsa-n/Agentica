#!/usr/bin/env bash
# =============================================================================
#  Prepares a Linux machine so Agentica can manage it over SSH.
#  Run ONCE on each Linux machine, as root:   sudo bash enable-agentica-target.sh
#
#  What it does:
#    1. Installs openssh-server and python3 if they are missing (apt / dnf / yum / zypper).
#    2. Creates a local user for Agentica (default: agentica). You choose its password.
#    3. Lets that user run ONLY `systemctl start|stop|restart <service>` as root without a
#       password (/etc/sudoers.d/agentica, validated with visudo). Nothing else.
#    4. Allows password sign-in over SSH for that user only (sshd drop-in), starts SSH.
#    5. Opens TCP 22 in ufw / firewalld if one is active (optionally only from --from <ip>).
#    6. Prints what to type into Agentica (Machines > +).
#
#  Options:  --user NAME        account name (default agentica)
#            --from IP          only allow SSH from the Agentica PC's IP (ufw / firewalld)
#            --no-create-user   use an existing account (it needs sudo rights for systemctl)
#
#  Undo with disable-agentica-target.sh. Nothing is installed for Agentica itself.
# =============================================================================
set -euo pipefail

USER_NAME="agentica"
FROM_IP=""
CREATE_USER=1
MARKER="Agentica remote management"

while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_NAME="${2:-}"; shift 2 ;;
    --from) FROM_IP="${2:-}"; shift 2 ;;
    --no-create-user) CREATE_USER=0; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

fail() { printf '\n  %s\n\n' "$1" >&2; exit 1; }
step() { printf '  > %s\n' "$1"; }

[ "$(id -u)" -eq 0 ] || fail "Run this script as root:  sudo bash $0"

# ---------------------------------------------------------------- checks (nothing changed yet)
if ! printf '%s' "$USER_NAME" | grep -Eq '^[a-z_][a-z0-9_-]{0,31}$'; then
  fail "Invalid user name '$USER_NAME' (lowercase letters, digits, _ or -, max 32). Nothing was changed."
fi
if [ "$CREATE_USER" -eq 1 ] && id "$USER_NAME" >/dev/null 2>&1; then
  gecos="$(getent passwd "$USER_NAME" | cut -d: -f5)"
  if [ "$gecos" != "$MARKER" ]; then
    fail "A user named '$USER_NAME' already exists and was not created by this script, so it will not be modified.
  Pick another name with --user, or use it as-is with --no-create-user. Nothing was changed."
  fi
fi
if [ -n "$FROM_IP" ] && ! printf '%s' "$FROM_IP" | grep -Eq '^[0-9a-fA-F.:/]+$'; then
  fail "--from must be an IP address (or CIDR). Nothing was changed."
fi

PASSWORD=""
if [ "$CREATE_USER" -eq 1 ]; then
  for try in 1 2 3; do
    read -r -s -p "  Choose a password for '$USER_NAME': " p1; echo
    read -r -s -p "  Type it again to confirm: " p2; echo
    if [ -z "$p1" ]; then echo "  The password cannot be empty."
    elif [ "$p1" != "$p2" ]; then echo "  The passwords don't match. Try again."
    else PASSWORD="$p1"; break; fi
  done
  [ -n "$PASSWORD" ] || fail "No password was set. Nothing was changed."
fi

printf '\nAgentica target setup on %s\n\n' "$(hostname)"

# ---------------------------------------------------------------- 1. packages
install_pkgs() {
  if command -v apt-get >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
       DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
  elif command -v dnf >/dev/null; then dnf install -y -q "$@"
  elif command -v yum >/dev/null; then yum install -y -q "$@"
  elif command -v zypper >/dev/null; then zypper --non-interactive install "$@"
  else fail "No supported package manager found; install $* manually."; fi
}
missing=()
command -v sshd >/dev/null || [ -x /usr/sbin/sshd ] || missing+=(openssh-server)
command -v python3 >/dev/null || missing+=(python3)
if [ ${#missing[@]} -gt 0 ]; then step "Installing ${missing[*]}"; install_pkgs "${missing[@]}"; fi

# ---------------------------------------------------------------- 2. user
ACCOUNT="$USER_NAME"
if [ "$CREATE_USER" -eq 1 ]; then
  if id "$USER_NAME" >/dev/null 2>&1; then
    step "Updating the password of the existing Agentica user '$USER_NAME'"
  else
    step "Creating user '$USER_NAME'"
    useradd -m -s /bin/bash -c "$MARKER" "$USER_NAME"
  fi
  printf '%s:%s\n' "$USER_NAME" "$PASSWORD" | chpasswd
  passwd -u "$USER_NAME" >/dev/null 2>&1 || true

  # ---------------------------------------------------------------- 3. sudo: systemctl start/stop/restart only
  SYSTEMCTL="$(command -v systemctl)"
  step "Allowing '$USER_NAME' to run only: systemctl start|stop|restart <service>"
  tmp="$(mktemp)"
  cat > "$tmp" <<EOF
# Created by Agentica's enable-agentica-target.sh. Remove with disable-agentica-target.sh.
$USER_NAME ALL=(root) NOPASSWD: $SYSTEMCTL start *, $SYSTEMCTL stop *, $SYSTEMCTL restart *
EOF
  visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; fail "sudoers rule failed validation; nothing was installed for sudo."; }
  install -m 0440 "$tmp" /etc/sudoers.d/agentica
  rm -f "$tmp"
fi

# ---------------------------------------------------------------- 4. SSH
if [ -d /etc/ssh/sshd_config.d ] && grep -Eq '^\s*Include\s+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config; then
  step "Allowing password sign-in over SSH for '$USER_NAME' only"
  printf '# Created by Agentica (enable-agentica-target.sh)\nMatch User %s\n    PasswordAuthentication yes\n' \
    "$USER_NAME" > /etc/ssh/sshd_config.d/60-agentica.conf
fi
if command -v sshd >/dev/null || [ -x /usr/sbin/sshd ]; then
  (command -v sshd >/dev/null && sshd -t) || /usr/sbin/sshd -t || fail "sshd configuration test failed."
fi
step "Starting the SSH service"
systemctl enable --now ssh >/dev/null 2>&1 || systemctl enable --now sshd >/dev/null 2>&1 || true
systemctl reload ssh >/dev/null 2>&1 || systemctl reload sshd >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 5. firewall
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  step "Opening TCP 22 in ufw${FROM_IP:+ (from $FROM_IP)}"
  if [ -n "$FROM_IP" ]; then ufw allow from "$FROM_IP" to any port 22 proto tcp >/dev/null
  else ufw allow 22/tcp >/dev/null; fi
elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  step "Opening TCP 22 in firewalld${FROM_IP:+ (from $FROM_IP)}"
  if [ -n "$FROM_IP" ]; then
    firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=$FROM_IP port port=22 protocol=tcp accept" >/dev/null
  else firewall-cmd --permanent --add-service=ssh >/dev/null; fi
  firewall-cmd --reload >/dev/null
fi

# ---------------------------------------------------------------- 6. summary
IPS="$(hostname -I 2>/dev/null | xargs || true)"
printf '\nDone. In Agentica: Machines > + and enter:\n'
printf '  Machine     : %s   (or %s)\n' "$(hostname)" "${IPS:-its IP address}"
printf '  OS          : Linux\n'
printf '  Connection  : SSH / 22\n'
printf '  Username    : %s\n' "$ACCOUNT"
if [ "$CREATE_USER" -eq 1 ]; then printf '  Password    : the password you just chose\n\n'
else printf '  Password    : that account'"'"'s password (it needs sudo rights for systemctl)\n\n'; fi
