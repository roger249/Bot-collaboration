#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Edit these values once
# -----------------------------
GHCR_OWNER="roger249"
IMAGE_NAME="planbot-proposal-server"

# Pin this to the released image tag (example: v20260811-abc1234)
IMAGE_TAG="v20260811-77f18f6"

# Compose env file used by docker compose
ENV_FILE=".env"

# -----------------------------
# Runtime checks
# -----------------------------
if [[ "${GHCR_OWNER}" == "<org-or-user>" ]]; then
  echo "Set GHCR_OWNER at the top of docker/deploy_linux.sh before running."
  exit 1
fi

if [[ "${IMAGE_TAG}" == "vYYYYMMDD-<gitsha>" ]]; then
  echo "Set IMAGE_TAG at the top of docker/deploy_linux.sh before running."
  exit 1
fi

if [[ -z "${GHCR_TOKEN:-}" ]]; then
  echo "GHCR_TOKEN is not set. Export it before running this script."
  exit 1
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is not set. Export it before running this script."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not in PATH."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is not available."
  exit 1
fi

if [[ ! -f "docker-compose.yml" ]]; then
  echo "Run this script from the repository root (docker-compose.yml not found)."
  exit 1
fi

IMAGE_REPO="ghcr.io/${GHCR_OWNER}/${IMAGE_NAME}"

cat > "${ENV_FILE}" <<EOF
IMAGE_REPO=${IMAGE_REPO}
IMAGE_TAG=${IMAGE_TAG}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
EOF

echo "Wrote ${ENV_FILE} with IMAGE_REPO and IMAGE_TAG"

echo "Logging in to GHCR as ${GHCR_OWNER}"
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_OWNER}" --password-stdin

echo "Pulling image ${IMAGE_REPO}:${IMAGE_TAG}"
docker compose pull

echo "Starting service"
docker compose up -d

echo "Deployment complete"
docker compose ps