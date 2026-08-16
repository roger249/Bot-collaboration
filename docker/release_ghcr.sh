#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root (parent of this script's directory) so the build
# context always points at the repo root, where the Dockerfile lives, no
# matter which directory the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# -----------------------------
# Edit these values once
# -----------------------------
GHCR_OWNER="roger249"
IMAGE_NAME="planbot-proposal-server"

# -----------------------------
# Platform switch
# -----------------------------
# Usage: ./release_ghcr.sh [amd64|arm64] [publish|local]
# Defaults to AMD64.  Pass "arm64" to build for ARM (e.g. Apple Silicon / ARM
# servers) for testing.
TARGET_ARCH="${1:-amd64}"
case "${TARGET_ARCH}" in
  amd64)
    PLATFORMS="linux/amd64"
    BUILDER_NAME="amd64-builder"
    ;;
  arm64)
    PLATFORMS="linux/arm64"
    BUILDER_NAME="arm64-builder"
    ;;
  *)
    echo "Unknown architecture: ${TARGET_ARCH}"
    echo "Usage: $0 [amd64|arm64] [publish|local]"
    exit 1
    ;;
esac

# -----------------------------
# Publish switch
# -----------------------------
# Usage: ./release_ghcr.sh [amd64|arm64] [publish|local]
# Defaults to "publish" (build and push to GHCR).  Pass "local" to build only
# and load the image into the local Docker daemon (no push, no GHCR token).
PUBLISH_MODE="${2:-publish}"
case "${PUBLISH_MODE}" in
  publish)
    PUSH_FLAG="--push"
    ;;
  local)
    PUSH_FLAG="--load"
    ;;
  *)
    echo "Unknown publish mode: ${PUBLISH_MODE}"
    echo "Usage: $0 [amd64|arm64] [publish|local]"
    exit 1
    ;;
esac

# Single-platform build.  buildx is still used because the build
# runs on Apple Silicon and must cross-compile to the target platform.

# Tag format: vYYYYMMDD-<gitsha>[-<arch>]
# The arch suffix is appended so AMD and ARM images can coexist under the
# same date+sha without one overwriting the other.
DATE_TAG="$(date +%Y%m%d)"
GIT_SHA="$(git rev-parse --short HEAD)"
IMAGE_TAG="v${DATE_TAG}-${GIT_SHA}-${TARGET_ARCH}"

# Optional: also publish latest pointer
PUBLISH_LATEST="false"

# -----------------------------
# Runtime checks
# -----------------------------
if [[ "${GHCR_OWNER}" == "<org-or-user>" ]]; then
  echo "Set GHCR_OWNER at the top of docker/release_ghcr.sh before running."
  exit 1
fi

if [[ "${PUBLISH_MODE}" == "publish" && -z "${GHCR_TOKEN:-}" ]]; then
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

if [[ "${PUBLISH_MODE}" == "publish" ]]; then
  echo "Logging in to GHCR as ${GHCR_OWNER}"
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_OWNER}" --password-stdin
fi

if [[ "${PUBLISH_MODE}" == "publish" ]]; then
  echo "Building and pushing ${IMAGE_REF} for ${PLATFORMS}"
else
  echo "Building ${IMAGE_REF} for ${PLATFORMS} (local only)"
fi
docker buildx build \
  --platform "${PLATFORMS}" \
  -t "${IMAGE_REF}" \
  ${PUSH_FLAG} \
  .

if [[ "${PUBLISH_MODE}" == "publish" && "${PUBLISH_LATEST}" == "true" ]]; then
  echo "Publishing latest tag"
  docker buildx build \
    --platform "${PLATFORMS}" \
    -t "${IMAGE_REPO}:latest" \
    --push \
    .
fi

if [[ "${PUBLISH_MODE}" == "publish" ]]; then
  echo "Verifying pushed image"
  docker buildx imagetools inspect "${IMAGE_REF}"
fi

echo
echo "Build completed"
echo "IMAGE_REPO=${IMAGE_REPO}"
echo "IMAGE_TAG=${IMAGE_TAG}"
echo "PUBLISH_MODE=${PUBLISH_MODE}"
if [[ "${PUBLISH_MODE}" == "publish" ]]; then
  echo
  echo "compose.yaml is embedded in the image."
  echo "Clients extract it with the command in README.md."
fi