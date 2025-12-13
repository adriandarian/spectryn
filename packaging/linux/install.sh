#!/usr/bin/env bash
# ==============================================================================
# md2jira Universal Linux Installer
# ==============================================================================
# 
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/adriandarian/md2jira/main/packaging/linux/install.sh | bash
#
# Or with a specific version:
#   curl -fsSL ... | bash -s -- --version 2.0.0
#
# ==============================================================================

set -euo pipefail

VERSION="${MD2JIRA_VERSION:-latest}"
INSTALL_METHOD="${MD2JIRA_INSTALL_METHOD:-pip}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --version|-v)
            VERSION="$2"
            shift 2
            ;;
        --method|-m)
            INSTALL_METHOD="$2"
            shift 2
            ;;
        --help|-h)
            echo "md2jira Installer"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --version, -v VERSION  Install specific version (default: latest)"
            echo "  --method, -m METHOD    Installation method: pip, pipx (default: pip)"
            echo "  --help, -h             Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check Python version
check_python() {
    log_info "Checking Python installation..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python 3.10+ is required but not found."
        log_info "Install Python using your package manager:"
        log_info "  Ubuntu/Debian: sudo apt install python3 python3-pip"
        log_info "  Fedora:        sudo dnf install python3 python3-pip"
        log_info "  Arch:          sudo pacman -S python python-pip"
        log_info "  macOS:         brew install python@3.12"
        exit 1
    fi
    
    # Check version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [[ "$MAJOR" -lt 3 ]] || [[ "$MAJOR" -eq 3 && "$MINOR" -lt 10 ]]; then
        log_error "Python 3.10+ is required, but found Python $PYTHON_VERSION"
        exit 1
    fi
    
    log_success "Found Python $PYTHON_VERSION"
}

# Install via pip
install_pip() {
    log_info "Installing md2jira via pip..."
    
    if [[ "$VERSION" == "latest" ]]; then
        $PYTHON_CMD -m pip install --upgrade md2jira
    else
        $PYTHON_CMD -m pip install --upgrade "md2jira==$VERSION"
    fi
    
    log_success "md2jira installed successfully!"
}

# Install via pipx (isolated environment)
install_pipx() {
    log_info "Installing md2jira via pipx..."
    
    # Check if pipx is installed
    if ! command -v pipx &> /dev/null; then
        log_info "pipx not found, installing..."
        $PYTHON_CMD -m pip install --user pipx
        $PYTHON_CMD -m pipx ensurepath
    fi
    
    if [[ "$VERSION" == "latest" ]]; then
        pipx install md2jira --force
    else
        pipx install "md2jira==$VERSION" --force
    fi
    
    log_success "md2jira installed successfully via pipx!"
}

# Verify installation
verify_install() {
    log_info "Verifying installation..."
    
    if command -v md2jira &> /dev/null; then
        INSTALLED_VERSION=$(md2jira --version 2>/dev/null | head -1)
        log_success "md2jira is installed: $INSTALLED_VERSION"
    else
        log_warning "md2jira installed but not in PATH"
        log_info "You may need to restart your terminal or add ~/.local/bin to PATH"
        log_info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

# Show next steps
show_next_steps() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}Installation complete!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Set up your Jira credentials:"
    echo "   export JIRA_URL=\"https://your-company.atlassian.net\""
    echo "   export JIRA_EMAIL=\"your.email@company.com\""
    echo "   export JIRA_API_TOKEN=\"your-api-token\""
    echo ""
    echo "2. Run md2jira:"
    echo "   md2jira --markdown EPIC.md --epic PROJ-123"
    echo ""
    echo "3. For more info:"
    echo "   md2jira --help"
    echo "   https://github.com/adriandarian/md2jira"
    echo ""
}

# Main
main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "           md2jira Installer"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    check_python
    
    case "$INSTALL_METHOD" in
        pip)
            install_pip
            ;;
        pipx)
            install_pipx
            ;;
        *)
            log_error "Unknown install method: $INSTALL_METHOD"
            exit 1
            ;;
    esac
    
    verify_install
    show_next_steps
}

main "$@"

