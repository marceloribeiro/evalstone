#!/usr/bin/env bash
# Thin wrapper: the shared Next.js deploy lives in javascript/deploy-next.sh (APP_NAME = this directory).
cd "$(dirname "$0")" && exec ../deploy-next.sh "$@"
