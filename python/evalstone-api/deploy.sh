#!/usr/bin/env bash
# Deploy evalstone-api to the server in deploy.json.
# Clones the public monorepo into releases/<ts>/ and points `current` at its python/evalstone-api
# package: .env → venv → alembic → current → restart units. Create-only on the server; never touches
# another app's files. Shared across releases: shared/logs, shared/certs (TLS).
set -e

ENVIRONMENT="${1:-production}"
CONFIG_FILE="deploy.json"
[ -f "$CONFIG_FILE" ] || { echo "❌ $CONFIG_FILE not found"; exit 1; }

VARS_FILE="$(mktemp -t evalstone_api_deploy_vars.XXXXXX)"
python3 - "$CONFIG_FILE" "$ENVIRONMENT" > "$VARS_FILE" <<'PYEOF'
import datetime, json, sys
cfg = json.load(open(sys.argv[1]))[sys.argv[2]]
ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
print(f'export DEPLOY_SERVER="{cfg["server"]}"')
print(f'export DEPLOY_GITHUB="{cfg["github"]}"')
print(f'export DEPLOY_PACKAGE="{cfg["package_path"]}"')
print(f'export DEPLOY_LOCATION="{cfg["deploy_location"]}"')
print(f'export DEPLOY_BRANCH="{cfg.get("deploy_branch", "main")}"')
print(f'export DEPLOY_RELEASE_PATH="{cfg["deploy_location"]}/releases/{ts}"')
print(f'export DEPLOY_TIMESTAMP="{ts}"')
print(f'export DEPLOY_SERVICES="{" ".join(cfg["services"])}"')
PYEOF
source "$VARS_FILE"; rm -f "$VARS_FILE"
APP_PATH="$DEPLOY_RELEASE_PATH/$DEPLOY_PACKAGE"

echo "🚀 evalstone-api → $DEPLOY_SERVER  ($DEPLOY_LOCATION, branch $DEPLOY_BRANCH, release $DEPLOY_TIMESTAMP)"

ENV_FILE=".env.$ENVIRONMENT"
[ -f "$ENV_FILE" ] || { echo "❌ $ENV_FILE missing — the operator supplies production secrets"; exit 1; }

ssh "$DEPLOY_SERVER" bash -s <<REMOTE
set -e
mkdir -p "$DEPLOY_LOCATION/releases" "$DEPLOY_LOCATION/shared/certs" "$DEPLOY_LOCATION/shared/logs"
rm -rf "$DEPLOY_RELEASE_PATH"
git clone -q --depth 1 --branch "$DEPLOY_BRANCH" "$DEPLOY_GITHUB" "$DEPLOY_RELEASE_PATH"
cd "$APP_PATH"
rm -rf logs && ln -sfn "$DEPLOY_LOCATION/shared/logs" logs
echo "✅ cloned \$(git -C "$DEPLOY_RELEASE_PATH" rev-parse --short HEAD)"
REMOTE

scp -q "$ENV_FILE" "$DEPLOY_SERVER:$APP_PATH/.env"
echo "✅ .env shipped"

ssh "$DEPLOY_SERVER" bash -s <<REMOTE
set -e
cd "$APP_PATH"
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "✅ venv ready"
./venv/bin/alembic upgrade head
echo "✅ migrated"
ln -sfn "$APP_PATH" "$DEPLOY_LOCATION/current.tmp" && mv -T "$DEPLOY_LOCATION/current.tmp" "$DEPLOY_LOCATION/current"
cd "$DEPLOY_LOCATION/releases" && ls -t | tail -n +4 | xargs -r rm -rf
echo "✅ current → releases/$DEPLOY_TIMESTAMP/$DEPLOY_PACKAGE (kept last 3)"
for unit in $DEPLOY_SERVICES; do
  if systemctl list-unit-files | grep -q "^\$unit.service"; then
    sudo systemctl restart "\$unit" && echo "✅ \$unit restarted"
  else
    echo "⚠️  \$unit not installed yet — run: just setup-systemd"
  fi
done
REMOTE
echo "🎉 done"
