#!/bin/sh
set -eu

# Build effective config/data folders from baked defaults plus optional overrides.
rm -rf /app/config /app/data
cp -a /app/config-default /app/config
cp -a /app/data-default /app/data

if [ -d /app/config-override ] && [ "$(ls -A /app/config-override 2>/dev/null || true)" ]; then
  /app/.venv/bin/python /app/merge_yaml.py /app/config-override /app/config
fi

if [ -d /app/data-override ] && [ "$(ls -A /app/data-override 2>/dev/null || true)" ]; then
  /app/.venv/bin/python /app/merge_yaml.py /app/data-override /app/data
fi

exec "$@"
