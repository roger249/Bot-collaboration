#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Edit these values once
# -----------------------------
GHCR_OWNER="roger249"
IMAGE_NAME="planbot-proposal-server"
PLATFORMS="linux/amd64,linux/arm64"
BUILDER_NAME="multiarch-builder"

# Tag format: vYYYYMMDD-<gitsha>
DATE_TAG="$(date +%Y%m%d)"
GIT_SHA="$(git rev-parse --short HEAD)"
IMAGE_TAG="v${DATE_TAG}-${GIT_SHA}"

# Optional: also publish latest pointer
PUBLISH_LATEST="false"

# -----------------------------
# Runtime checks
# -----------------------------
if [[ "${GHCR_OWNER}" == "<org-or-user>" ]]; then
  echo "Set GHCR_OWNER at the top of docker/release_ghcr.sh before running."
  exit 1
fi

if [[ -z "${GHCR_TOKEN:-}" ]]; then
  echo "GHCR_TOKEN is not set. Export it before running this script."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not in PATH."
  exit 1
fi

if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
  docker buildx create --name "${BUILDER_NAME}" --use
else
  docker buildx use "${BUILDER_NAME}"
fi

docker buildx inspect --bootstrap >/dev/null

IMAGE_REPO="ghcr.io/${GHCR_OWNER}/${IMAGE_NAME}"
IMAGE_REF="${IMAGE_REPO}:${IMAGE_TAG}"

echo "Logging in to GHCR as ${GHCR_OWNER}"
echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_OWNER}" --password-stdin

echo "Building and pushing ${IMAGE_REF} for ${PLATFORMS}"
docker buildx build \
  --platform "${PLATFORMS}" \
  -t "${IMAGE_REF}" \
  --push \
  .

if [[ "${PUBLISH_LATEST}" == "true" ]]; then
  echo "Publishing latest tag"
  docker buildx build \
    --platform "${PLATFORMS}" \
    -t "${IMAGE_REPO}:latest" \
    --push \
    .
fi

echo "Verifying pushed manifest"
docker buildx imagetools inspect "${IMAGE_REF}"

echo
echo "Release completed"
echo "IMAGE_REPO=${IMAGE_REPO}"
echo "IMAGE_TAG=${IMAGE_TAG}"