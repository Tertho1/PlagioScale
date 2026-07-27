#!/usr/bin/env bash
set -euo pipefail

# PlagioScale Deploy Script
# Pulls pre-built GHCR images and starts all services.
#
# Usage:
#   bash scripts/deploy.sh
#
# Environment variables:
#   IMAGE_OWNER — GitHub owner (default: anomalye co)
#   IMAGE_TAG  — image tag to deploy (default: latest)

IMAGE_OWNER="${IMAGE_OWNER:-${GITHUB_REPOSITORY_OWNER:-anomalyco}}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

cd "$(dirname "$0")/.."

echo "==> PlagioScale Deploy — ghcr.io/$IMAGE_OWNER:$IMAGE_TAG"
echo ""

# Pull pre-built images
echo "==> Pulling images..."
IMAGE_REPO=ghcr.io IMAGE_OWNER=$IMAGE_OWNER IMAGE_TAG=$IMAGE_TAG \
  docker compose pull

# Start services (skip build — we pulled)
echo "==> Starting services..."
IMAGE_REPO=ghcr.io IMAGE_OWNER=$IMAGE_OWNER IMAGE_TAG=$IMAGE_TAG \
  docker compose up --no-build -d

echo ""
echo "==> Done.  docker compose ps  to check status."
echo "    Dashboard: http://localhost:3050"
echo "    Grafana:   http://localhost:3000 (admin:${GRAFANA_PASSWORD:-admin})"
