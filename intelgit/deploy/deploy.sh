#!/usr/bin/env bash
# One-click deployment for IntelGit Registry
# Supports Fly.io and Railway

set -euo pipefail

REGISTRY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/intelgit-registry"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: $0 [fly|railway|both] [OPTIONS]

Commands:
  fly       Deploy to Fly.io
  railway   Deploy to Railway
  both      Deploy to both platforms (default)

Options:
  --app-name NAME    App name (default: intelgit-registry)
  --region REGION    Fly.io region (default: ord)
  --dry-run          Print commands without executing
  --help             Show this help

Environment variables:
  FLY_API_TOKEN      Fly.io API token (or run: fly auth login)
  RAILWAY_TOKEN      Railway token (or run: railway login)

Examples:
  $0 fly --app-name my-registry
  $0 railway
  $0 both --dry-run
EOF
    exit 0
}

# Defaults
TARGET="both"
APP_NAME="intelgit-registry"
REGION="ord"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        fly|railway|both) TARGET="$1"; shift ;;
        --app-name) APP_NAME="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage ;;
        *) error "Unknown argument: $1" ;;
    esac
done

run() {
    if $DRY_RUN; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $*"
    else
        "$@"
    fi
}

check_docker() {
    if ! command -v docker &>/dev/null; then
        error "Docker is required. Install from https://docs.docker.com/get-docker/"
    fi
    success "Docker found: $(docker --version | head -1)"
}

# ─── FLY.IO ────────────────────────────────────────────────────────────────────

install_flyctl() {
    if command -v fly &>/dev/null; then
        success "flyctl found: $(fly version | head -1)"
        return
    fi
    info "Installing flyctl..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            run brew install flyctl
        else
            run curl -L https://fly.io/install.sh | sh
        fi
    else
        run curl -L https://fly.io/install.sh | sh
    fi
    export PATH="$HOME/.fly/bin:$PATH"
    success "flyctl installed"
}

deploy_fly() {
    info "=== Deploying to Fly.io ==="
    install_flyctl

    if [[ -z "${FLY_API_TOKEN:-}" ]]; then
        warn "FLY_API_TOKEN not set. Attempting interactive login..."
        run fly auth login
    fi

    cd "$REGISTRY_DIR"

    # Patch fly.toml with the chosen app name and region
    if [[ -f fly.toml ]]; then
        if $DRY_RUN; then
            echo -e "${YELLOW}[DRY-RUN]${NC} Would update fly.toml: app=${APP_NAME}, region=${REGION}"
        else
            sed -i.bak \
                -e "s/^app = .*/app = \"${APP_NAME}\"/" \
                -e "s/primary_region = .*/primary_region = \"${REGION}\"/" \
                fly.toml
            rm -f fly.toml.bak
            success "Updated fly.toml (app=${APP_NAME}, region=${REGION})"
        fi
    fi

    # Create app if it doesn't exist
    if ! fly apps list 2>/dev/null | grep -q "^${APP_NAME}"; then
        info "Creating Fly app: ${APP_NAME}"
        run fly apps create "${APP_NAME}" --org personal
    else
        info "Fly app '${APP_NAME}' already exists"
    fi

    # Create volume for persistent data
    if ! fly volumes list --app "${APP_NAME}" 2>/dev/null | grep -q "intelgit_data"; then
        info "Creating persistent volume..."
        run fly volumes create intelgit_data --app "${APP_NAME}" --region "${REGION}" --size 1
    else
        info "Volume 'intelgit_data' already exists"
    fi

    # Set secrets
    if [[ -z "${FLY_API_TOKEN:-}" ]]; then
        info "Setting Fly secrets..."
        run fly secrets set \
            INTELGIT_DATA="/data" \
            PAYMENT_PROVIDER="local" \
            --app "${APP_NAME}"
    fi

    # Deploy
    info "Deploying..."
    run fly deploy --app "${APP_NAME}" --remote-only

    REGISTRY_URL="https://${APP_NAME}.fly.dev"
    success "Deployed to Fly.io: ${REGISTRY_URL}"
    echo ""
    echo "  Configure your client:"
    echo "    ko config set registry_url ${REGISTRY_URL}"
    echo "    ko login --registry ${REGISTRY_URL}"
}

# ─── RAILWAY ───────────────────────────────────────────────────────────────────

install_railway() {
    if command -v railway &>/dev/null; then
        success "Railway CLI found: $(railway --version 2>&1 | head -1)"
        return
    fi
    info "Installing Railway CLI..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            run brew install railway
        else
            run curl -fsSL https://railway.app/install.sh | sh
        fi
    else
        run curl -fsSL https://railway.app/install.sh | sh
    fi
    success "Railway CLI installed"
}

deploy_railway() {
    info "=== Deploying to Railway ==="
    install_railway

    if [[ -z "${RAILWAY_TOKEN:-}" ]]; then
        warn "RAILWAY_TOKEN not set. Attempting interactive login..."
        run railway login
    fi

    cd "$REGISTRY_DIR"

    # Ensure railway.toml is present
    if [[ ! -f railway.toml ]]; then
        info "Creating railway.toml..."
        if ! $DRY_RUN; then
            cat > railway.toml <<RAILEOF
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn src.main:app --host 0.0.0.0 --port \$PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[[services]]
name = "${APP_NAME}"

[services.variables]
INTELGIT_DATA = "/data"
PAYMENT_PROVIDER = "local"
RAILEOF
        fi
        success "Created railway.toml"
    fi

    # Initialize project if needed
    if [[ ! -f .railway ]]; then
        info "Initializing Railway project..."
        run railway init --name "${APP_NAME}"
    fi

    # Deploy
    info "Deploying to Railway..."
    run railway up --detach

    success "Deployed to Railway!"
    echo ""
    info "Get your Railway URL with: railway domain"
    echo "  Then configure your client:"
    echo "    ko config set registry_url <your-railway-url>"
    echo "    ko login --registry <your-railway-url>"
}

# ─── MAIN ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ██╗███╗   ██╗████████╗███████╗██╗      ██████╗ ██╗████████╗"
echo "  ██║████╗  ██║╚══██╔══╝██╔════╝██║     ██╔════╝ ██║╚══██╔══╝"
echo "  ██║██╔██╗ ██║   ██║   █████╗  ██║     ██║  ███╗██║   ██║   "
echo "  ██║██║╚██╗██║   ██║   ██╔══╝  ██║     ██║   ██║██║   ██║   "
echo "  ██║██║ ╚████║   ██║   ███████╗███████╗╚██████╔╝██║   ██║   "
echo "  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚══════╝ ╚═════╝ ╚═╝   ╚═╝   "
echo ""
echo "  IntelGit Registry – One-Click Deploy"
echo ""

check_docker

case "$TARGET" in
    fly)     deploy_fly ;;
    railway) deploy_railway ;;
    both)    deploy_fly; echo ""; deploy_railway ;;
esac

echo ""
success "Deployment complete!"
