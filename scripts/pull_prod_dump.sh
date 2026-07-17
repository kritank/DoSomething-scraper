#!/usr/bin/env bash
#
# Pulls a full SQL dump of the production "viralytics-db" RDS instance to a
# local file, via an SSH tunnel through the app EC2 box.
#
# Why the tunnel: RDS's security group (viralytics-rds-sg) only allows inbound
# 5432 from the app EC2 instance's SG (see infra/rds.tf) — it has no public
# endpoint. The EC2 box is itself restricted to admin_cidr_block for SSH
# (infra/ec2.tf). So pg_dump can't hit RDS directly from a laptop; it has to
# go through the EC2 box as a bastion.
#
# Usage:
#   ./scripts/pull_prod_dump.sh --db-host <rds-endpoint> --ssh-key ~/Downloads/serevr.pem --db-password '***'
#
# --db-password is visible to other local users via `ps` for the life of the
# process (it's only used to set PGPASSWORD before each pg_dump invocation).
# If that matters on your machine, omit the flag and the script will prompt
# for it instead (not echoed).
#
# Get RDS_HOST with:  cd infra && terraform output rds_endpoint
#
set -euo pipefail

# ── Defaults (override via flags or env vars) ────────────────────────────────
EC2_HOST="${EC2_HOST:-13.206.31.71}"       # elastic IP, see infra/outputs.tf
EC2_USER="${EC2_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-}"
RDS_HOST="${RDS_HOST:-}"
RDS_PORT="${RDS_PORT:-5432}"
DB_NAME="${DB_NAME:-viralytics_scrapper}" # infra/variables.tf default
DB_USER="${DB_USER:-postgres}"            # infra/variables.tf: actual master user
DB_PASSWORD="${DB_PASSWORD:-}"
FORMAT="custom"                            # custom (-Fc, compressed, restore with pg_restore) | plain (.sql.gz)
OUT_DIR="${OUT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/dumps}"
LOCAL_TUNNEL_PORT="${LOCAL_TUNNEL_PORT:-15432}"
JOBS="${JOBS:-4}"                          # parallel workers, directory-format dumps only

usage() {
  grep '^#' "${BASH_SOURCE[0]}" | sed -e 's/^#//' -e 's/^ //'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ec2-host) EC2_HOST="$2"; shift 2 ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    --db-host) RDS_HOST="$2"; shift 2 ;;
    --db-port) RDS_PORT="$2"; shift 2 ;;
    --db-name) DB_NAME="$2"; shift 2 ;;
    --db-user) DB_USER="$2"; shift 2 ;;
    --db-password) DB_PASSWORD="$2"; shift 2 ;;
    --format) FORMAT="$2"; shift 2 ;;      # custom | plain | directory
    --jobs) JOBS="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -z "$RDS_HOST" ]] && { echo "Error: --db-host (or RDS_HOST env var) is required. Get it with: cd infra && terraform output rds_endpoint" >&2; exit 1; }
[[ -z "$SSH_KEY" ]] && { echo "Error: --ssh-key (or SSH_KEY env var) is required — path to the .pem for $EC2_USER@$EC2_HOST" >&2; exit 1; }
[[ ! -f "$SSH_KEY" ]] && { echo "Error: SSH key not found at $SSH_KEY" >&2; exit 1; }

if [[ -z "$DB_PASSWORD" ]]; then
  read -r -s -p "Password for $DB_USER on $RDS_HOST: " DB_PASSWORD
  echo
fi

for bin in ssh pg_dump; do
  command -v "$bin" >/dev/null || { echo "Error: '$bin' not found on PATH" >&2; exit 1; }
done

mkdir -p "$OUT_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
CONTROL_SOCK="/tmp/pull_prod_dump_ssh_$$.sock"

cleanup() {
  if [[ -S "$CONTROL_SOCK" ]]; then
    echo "Closing SSH tunnel..."
    ssh -S "$CONTROL_SOCK" -O exit -o ConnectTimeout=5 "$EC2_USER@$EC2_HOST" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "Opening SSH tunnel through $EC2_USER@$EC2_HOST -> $RDS_HOST:$RDS_PORT ..."
ssh -i "$SSH_KEY" -f -N -M -S "$CONTROL_SOCK" \
    -o ExitOnForwardFailure=yes -o ConnectTimeout=10 \
    -L "${LOCAL_TUNNEL_PORT}:${RDS_HOST}:${RDS_PORT}" \
    "$EC2_USER@$EC2_HOST"

# Wait for the tunnel to actually accept connections before handing off to pg_dump.
for i in $(seq 1 20); do
  if (exec 3<>"/dev/tcp/127.0.0.1/${LOCAL_TUNNEL_PORT}") 2>/dev/null; then
    exec 3>&- 3<&-
    break
  fi
  [[ $i -eq 20 ]] && { echo "Error: tunnel never came up" >&2; exit 1; }
  sleep 0.5
done
echo "Tunnel is up on localhost:${LOCAL_TUNNEL_PORT}"

case "$FORMAT" in
  custom)
    OUT_FILE="$OUT_DIR/${DB_NAME}_${TIMESTAMP}.dump"
    echo "Dumping (custom format, compressed) to $OUT_FILE ..."
    PGPASSWORD="$DB_PASSWORD" pg_dump \
      -h 127.0.0.1 -p "$LOCAL_TUNNEL_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -Fc --no-owner --no-privileges -v \
      -f "$OUT_FILE"
    RESTORE_HINT="pg_restore --no-owner --no-privileges --clean --if-exists -d <local_db> \"$OUT_FILE\""
    ;;
  directory)
    OUT_FILE="$OUT_DIR/${DB_NAME}_${TIMESTAMP}_dir"
    echo "Dumping (directory format, $JOBS parallel jobs) to $OUT_FILE ..."
    PGPASSWORD="$DB_PASSWORD" pg_dump \
      -h 127.0.0.1 -p "$LOCAL_TUNNEL_PORT" -U "$DB_USER" -d "$DB_NAME" \
      -Fd -j "$JOBS" --no-owner --no-privileges -v \
      -f "$OUT_FILE"
    RESTORE_HINT="pg_restore --no-owner --no-privileges --clean --if-exists -j $JOBS -d <local_db> \"$OUT_FILE\""
    ;;
  plain)
    OUT_FILE="$OUT_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
    echo "Dumping (plain SQL, gzipped) to $OUT_FILE ..."
    PGPASSWORD="$DB_PASSWORD" pg_dump \
      -h 127.0.0.1 -p "$LOCAL_TUNNEL_PORT" -U "$DB_USER" -d "$DB_NAME" \
      --no-owner --no-privileges -v \
      | gzip > "$OUT_FILE"
    RESTORE_HINT="gunzip -c \"$OUT_FILE\" | psql <local_db>"
    ;;
  *)
    echo "Error: --format must be custom, directory, or plain" >&2
    exit 1
    ;;
esac

echo
echo "Done: $OUT_FILE"
echo "Restore locally with:"
echo "  $RESTORE_HINT"
