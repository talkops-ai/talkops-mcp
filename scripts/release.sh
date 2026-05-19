#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TalkOps MCP Server — Release Helper
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   ./scripts/release.sh <server-name> <version>
#
# Examples:
#   ./scripts/release.sh prometheus-mcp-server 0.2.0
#   ./scripts/release.sh helm-mcp-server 0.3.0
#
# What it does:
#   1. Validates the server exists and version format
#   2. Checks that pyproject.toml version matches
#   3. Creates a git tag: <server-name>/v<version>
#   4. Pushes the tag to trigger the release pipeline
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── Validation ────────────────────────────────────────────────────────────

if [ $# -lt 2 ]; then
    echo -e "${RED}Usage: $0 <server-name> <version>${NC}"
    echo ""
    echo "Available servers:"
    echo "  prometheus-mcp-server"
    echo "  alertmanager-mcp-server"
    echo "  helm-mcp-server"
    echo "  argocd-mcp-server"
    echo "  argo-rollout-mcp-server"
    echo "  kargo-mcp-server"
    echo "  traefik-mcp-server"
    echo ""
    echo "Example: $0 prometheus-mcp-server 0.2.0"
    exit 1
fi

SERVER_NAME="$1"
VERSION="$2"
SERVER_DIR="src/${SERVER_NAME}"
TAG="${SERVER_NAME}/v${VERSION}"

# Validate server exists
if [ ! -d "$SERVER_DIR" ]; then
    echo -e "${RED}❌ Server directory not found: ${SERVER_DIR}${NC}"
    exit 1
fi

# Validate pyproject.toml exists
PYPROJECT="${SERVER_DIR}/pyproject.toml"
if [ ! -f "$PYPROJECT" ]; then
    echo -e "${RED}❌ pyproject.toml not found: ${PYPROJECT}${NC}"
    exit 1
fi

# Validate version format (semver-like)
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9._-]*)?$'; then
    echo -e "${RED}❌ Invalid version format: ${VERSION}${NC}"
    echo "Expected format: X.Y.Z (e.g., 0.2.0, 1.0.0rc1)"
    exit 1
fi

# Check pyproject.toml version matches
TOML_VERSION=$(grep '^version' "$PYPROJECT" | head -1 | sed 's/.*"\(.*\)".*/\1/')
if [ "$TOML_VERSION" != "$VERSION" ]; then
    echo -e "${RED}❌ Version mismatch!${NC}"
    echo "   pyproject.toml: ${TOML_VERSION}"
    echo "   Requested:      ${VERSION}"
    echo ""
    echo -e "${YELLOW}Update ${PYPROJECT} first:${NC}"
    echo "   version = \"${VERSION}\""
    exit 1
fi

# Check for uncommitted changes in the server directory
if ! git diff --quiet HEAD -- "$SERVER_DIR"; then
    echo -e "${RED}❌ Uncommitted changes in ${SERVER_DIR}${NC}"
    echo "Commit your changes first."
    exit 1
fi

# Check if tag already exists
if git tag -l "$TAG" | grep -q .; then
    echo -e "${RED}❌ Tag already exists: ${TAG}${NC}"
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          TalkOps MCP Server Release          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  📦 Server:    ${GREEN}${SERVER_NAME}${NC}"
echo -e "  🏷️  Version:   ${GREEN}${VERSION}${NC}"
echo -e "  🔖 Git tag:   ${GREEN}${TAG}${NC}"
echo -e "  🐍 PyPI name: ${GREEN}talkops-${SERVER_NAME}${NC}"
echo ""

# ── Confirm ───────────────────────────────────────────────────────────────

read -rp "$(echo -e "${YELLOW}Create and push tag? [y/N] ${NC}")" CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

# ── Execute ───────────────────────────────────────────────────────────────

echo ""
echo -e "${BLUE}Creating tag: ${TAG}${NC}"
git tag -a "$TAG" -m "Release ${SERVER_NAME} v${VERSION}"

echo -e "${BLUE}Pushing tag to origin...${NC}"
git push origin "$TAG"

echo ""
echo -e "${GREEN}✅ Tag pushed! The release pipeline will now:${NC}"
echo "   1. Run tests"
echo "   2. Build sdist + wheel"
echo "   3. Publish to PyPI"
echo "   4. Create GitHub Release"
echo ""
echo -e "${BLUE}Track progress:${NC}"
echo "   https://github.com/talkops-ai/talkops-mcp/actions"
echo ""
echo -e "${GREEN}Once published, users can install with:${NC}"
echo "   pip install talkops-${SERVER_NAME}==${VERSION}"
echo "   uvx talkops-${SERVER_NAME}"
