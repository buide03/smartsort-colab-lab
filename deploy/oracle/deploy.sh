#!/usr/bin/env bash
# Run on the Ubuntu VM, from any working directory: bash deploy/oracle/deploy.sh
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! docker compose version >/dev/null 2>&1; then
  echo 'Install Docker Engine and Compose plugin first; see docs/DEPLOY_ORACLE.md.' >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo 'Created .env. Set your DNS hostname and classroom password, then rerun.' >&2
  exit 1
fi
chmod 600 .env
# Parse via Compose, never source a user-editable .env as shell code.
docker compose --env-file .env config --format json | python3 -c '
import json,sys,re
c=json.load(sys.stdin)
env=c["services"]["smartsort"]["environment"]
domain=c["services"]["caddy"]["environment"]["SMARTSORT_DOMAIN"]
if env["SMARTSORT_CLASSROOM_PASSWORD"]=="CHANGE_THIS_BEFORE_DEPLOY" or len(env["SMARTSORT_CLASSROOM_PASSWORD"])<10:
 sys.exit("Set a classroom password of at least 10 characters in .env.")
if domain=="your-lab.example.org" or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?",domain) or "." not in domain:
 sys.exit("Set an actual DNS hostname without https:// or a path.")
print("Configuration OK; data:",c["services"]["smartsort"]["volumes"][0]["source"])
'
docker compose --env-file .env up --build -d --wait --wait-timeout 240
docker compose --env-file .env ps
echo 'Open your HTTPS hostname. Check Caddy logs if the certificate is not yet available.'
