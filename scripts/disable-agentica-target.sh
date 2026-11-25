#!/usr/bin/env bash
# =============================================================================
#  Undoes enable-agentica-target.sh. Run as root:   sudo bash disable-agentica-target.sh
#
#  Removes the sudo rule and the sshd drop-in, and deletes the Agentica user (only a user that
#  enable-agentica-target.sh created). SSH itself is left running so you are not locked out.
#
#  Options:  --user NAME   (default agentica)     --keep-user   leave the account in place
# =============================================================================
set -euo pipefail
USER_NAME="agentica"
KEEP_USER=0
MARKER="Agentica remote management"
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_NAME="${2:-}"; shift 2 ;;
    --keep-user) KEEP_USER=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0" >&2; exit 1; }

printf '\nRemoving Agentica access from %s\n\n' "$(hostname)"
rm -f /etc/sudoers.d/agentica && echo "  > removed the sudo rule"
if [ -f /etc/ssh/sshd_config.d/60-agentica.conf ]; then
  rm -f /etc/ssh/sshd_config.d/60-agentica.conf && echo "  > removed the SSH password sign-in rule"
  systemctl reload ssh >/dev/null 2>&1 || systemctl reload sshd >/dev/null 2>&1 || true
fi
if [ "$KEEP_USER" -eq 0 ] && id "$USER_NAME" >/dev/null 2>&1; then
  if [ "$(getent passwd "$USER_NAME" | cut -d: -f5)" = "$MARKER" ]; then
    userdel -r "$USER_NAME" 2>/dev/null || userdel "$USER_NAME"
    echo "  > deleted the user '$USER_NAME'"
  else
    echo "  ! '$USER_NAME' was not created by enable-agentica-target.sh, so it was left untouched."
  fi
fi
printf 'Done. SSH is still running (stop it yourself if nothing else needs it).\n'
