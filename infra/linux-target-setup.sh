#!/usr/bin/env bash
# Idempotent: sets up agentica user, SSH key, scoped sudoers on a Linux target.
# Run as root on the target.
set -euo pipefail

AGENTICA_USER="agentica"
KEY_DIR="/home/${AGENTICA_USER}/.ssh"

# 1. Create user if missing
if ! id "${AGENTICA_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${AGENTICA_USER}"
  echo "Created user ${AGENTICA_USER}"
fi

# 2. Set up SSH directory
mkdir -p "${KEY_DIR}"
chown "${AGENTICA_USER}:${AGENTICA_USER}" "${KEY_DIR}"
chmod 700 "${KEY_DIR}"

# 3. Generate ed25519 key if missing
KEYFILE="${KEY_DIR}/id_ed25519"
if [ ! -f "${KEYFILE}" ]; then
  sudo -u "${AGENTICA_USER}" ssh-keygen -t ed25519 -N "" -f "${KEYFILE}"
  cat "${KEYFILE}.pub" >> "${KEY_DIR}/authorized_keys"
  chmod 600 "${KEY_DIR}/authorized_keys"
  echo "Generated SSH key at ${KEYFILE}"
fi

# 4. Scoped sudoers — only systemctl (no shell)
SUDOERS_FILE="/etc/sudoers.d/agentica"
cat > "${SUDOERS_FILE}" << 'SUDOERS'
# Agentica: allow systemctl operations without password, no shell
agentica ALL=(ALL) NOPASSWD: /bin/systemctl start *, /bin/systemctl stop *, /bin/systemctl restart *, /bin/systemctl status *, /bin/systemctl list-units *
SUDOERS
chmod 440 "${SUDOERS_FILE}"

# 5. Validate sudoers
visudo -c -f "${SUDOERS_FILE}"

echo "--- Agentica target setup complete ---"
echo "Private key (copy to Agentica keyring):"
cat "${KEYFILE}"
echo ""
echo "Public key:"
cat "${KEYFILE}.pub"
