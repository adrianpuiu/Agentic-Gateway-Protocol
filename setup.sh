#!/bin/bash
# Quick setup script for AGP
set -e

echo "=== AGP Setup ==="

# Check Python version
PYTHON=$(command -v python3 || command -v python)
PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Use virtual environment if it exists
if [ -d "venv" ]; then
    PYTHON="./venv/bin/python"
    PIP="./venv/bin/pip"
    echo "Using existing venv..."
else
    PIP="pip"
fi

# Install in editable mode
echo "Installing agp..."
$PIP install -e .

# Create default config
CONFIG_DIR="$HOME/.agp"
CONFIG_FILE="$CONFIG_DIR/config.json"
WORKSPACE_DIR="$CONFIG_DIR/workspace"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Creating default config..."
    mkdir -p "$WORKSPACE_DIR"
    cat > "$CONFIG_FILE" << EOF
{
  "workspace": "$WORKSPACE_DIR",
  "model": "sonnet",
  "channels": {
    "telegram": {
      "enabled": false,
      "token": "",
      "allow_from": []
    }
  }
}
EOF
    echo "Config created at: $CONFIG_FILE"
    echo "Workspace created at: $WORKSPACE_DIR"
    
    # Copy template memory files if they exist in local ./workspace
    if [ -d "workspace" ]; then
        echo "Copying template memory files to workspace..."
        cp -n workspace/*.md "$WORKSPACE_DIR/" 2>/dev/null || true
    fi

    echo ""
    echo "Edit config to add your:"
    echo "  - Claude API key (set ANTHROPIC_API_KEY env var)"
    echo "  - Telegram bot token (enable telegram channel)"
    echo "  - Your Telegram User ID (add to allow_from list)"
    echo ""
    echo "Example:"
    echo "  export ANTHROPIC_API_KEY='sk-ant-...'"
    echo "  # Add your ID to allow_from: [\"12345678\"]"
    echo "  nano $CONFIG_FILE"
else
    echo "Config already exists at: $CONFIG_FILE"
fi

echo ""
echo "=== Setup Complete ===="
echo ""
echo "Usage:"
echo "  agp status          # Show config and status"
echo "  agp agent -m '...'  # Single message"
echo "  agp gateway         # Start full server (Telegram, Cron, etc)"
echo ""
