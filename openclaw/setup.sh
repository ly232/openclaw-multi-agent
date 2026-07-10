#!/bin/bash
# =============================================================================
# OpenClaw Multi-Agent Setup Script
# =============================================================================
# Safely deploys the multi-agent configuration to ~/.openclaw
#
# What this does:
#   1. Backs up existing ~/.openclaw/openclaw.json
#   2. Copies workspace identity files (AGENTS.md, SOUL.md, etc.)
#   3. Generates a complete openclaw.json from template + local secrets
#   4. Generates per-agent models.json with your DeepSeek API key
#   5. Optionally initializes git tracking for ~/.openclaw/
#
# No sensitive data is stored in this repository. API keys and tokens
# are read from your existing OpenClaw config or environment variables.
#
# Usage:
#   chmod +x openclaw/setup.sh
#   ./openclaw/setup.sh              # preview mode (dry run)
#   ./openclaw/setup.sh --apply      # deploy everything
#   ./openclaw/setup.sh --git-init   # also git init ~/.openclaw
# =============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
APPLY=false
GIT_INIT=false

for arg in "$@"; do
  case "$arg" in
    --apply)    APPLY=true ;;
    --git-init) GIT_INIT=true ;;
    --help|-h)
      echo "Usage: $0 [--apply] [--git-init]"
      echo ""
      echo "  --apply      Actually copy files and generate config (default: dry-run)"
      echo "  --git-init   Also 'git init ~/.openclaw' for version tracking"
      echo ""
      echo "Environment variables:"
      echo "  DEEPSEEK_API_KEY    Set this if you don't have an existing config yet"
      echo ""
      echo "Examples:"
      echo "  # First time setup (no existing config):"
      echo "    export DEEPSEEK_API_KEY='sk-your-key'"
      echo "    ./openclaw/setup.sh --apply"
      echo ""
      echo "  # Upgrade existing config:"
      echo "    ./openclaw/setup.sh --apply"
      exit 0
      ;;
  esac
done

echo "============================================"
echo " OpenClaw Multi-Agent Setup"
echo "============================================"
echo ""
echo "Repo dir:      $REPO_DIR"
echo "OpenClaw dir:  $OPENCLAW_DIR"
echo "Mode:          $($APPLY && echo 'APPLY' || echo 'PREVIEW (dry-run)')"
echo ""

# ---- Check prerequisites ----
if ! command -v openclaw &>/dev/null; then
  echo "❌  openclaw CLI not found. Install OpenClaw first."
  exit 1
fi

if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "ℹ️  ~/.openclaw not found. Run 'openclaw onboard' first, then re-run this script."
  echo "    (Or run directly if you already have the config elsewhere.)"
fi

# ---- Step 1: Back up existing config ----
BACKUP="$OPENCLAW_DIR/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"
if [ -f "$OPENCLAW_DIR/openclaw.json" ]; then
  if $APPLY; then
    cp "$OPENCLAW_DIR/openclaw.json" "$BACKUP"
    echo "✅  Backed up config → $BACKUP"
  else
    echo "📋  Would backup config → $BACKUP"
  fi
fi

# ---- Step 2: Create workspace directories ----
WORKSPACES=("orchestrator" "coding" "research" "cs285" "general")
echo ""
echo "── Workspace Files ──"
for ws in "${WORKSPACES[@]}"; do
  TARGET="$OPENCLAW_DIR/workspaces/$ws"
  SOURCE="$REPO_DIR/openclaw/workspaces/$ws"
  if $APPLY; then
    mkdir -p "$TARGET"
    if [ -d "$SOURCE" ]; then
      cp -R "$SOURCE/"* "$TARGET/" 2>/dev/null || true
    fi
    # Create USER.md from example if not present
    if [ ! -f "$TARGET/USER.md" ] && [ -f "$SOURCE/USER.md.example" ]; then
      cp "$SOURCE/USER.md.example" "$TARGET/USER.md"
      echo "  📝 $ws: created USER.md from template (edit with your details)"
    fi
    echo "✅  Workspace '$ws' → $TARGET"
  else
    echo "📋  Would copy workspace '$ws': $SOURCE/ → $TARGET/"
  fi
done

# ---- Step 3: Create agent directories ----
echo ""
echo "── Agent Directories ──"
for agent in "${WORKSPACES[@]}"; do
  TARGET="$OPENCLAW_DIR/agents/$agent/agent"
  if $APPLY; then
    mkdir -p "$TARGET"
    echo "✅  Agent dir '$agent' → $TARGET"
  else
    echo "📋  Would create agent dir '$agent' → $TARGET"
  fi
done

# ---- Step 4: Generate config + per-agent models.json ----
echo ""
echo "── Configuration ──"
if $APPLY; then
  echo "Generating config from template..."
  "$REPO_DIR/generate-config.sh" --output
  echo ""
  echo "✅  Config and per-agent models.json generated."
  echo "   (Your existing gateway, auth, and model settings were preserved.)"
else
  echo "📋  Would run: $REPO_DIR/generate-config.sh --output"
  echo "    (Generates openclaw.json + per-agent models.json with your API key)"
fi

# ---- Step 5: Restart gateway ----
echo ""
echo "── Gateway Restart ──"
if $APPLY; then
  echo "Restarting gateway..."
  # Try graceful restart; ignore errors (gateway might not be running yet)
  openclaw gateway restart 2>/dev/null || echo "  ⚠️  Gateway restart skipped (might not be running)."
  echo ""
  echo "✅  Done! Verify with:"
  echo ""
  echo "    openclaw agents list"
  echo "    openclaw channels status --probe"
else
  echo "📋  After applying, restart the gateway:"
  echo "      openclaw gateway restart"
  echo ""
  echo "  Then verify:"
  echo "      openclaw agents list"
  echo "      openclaw channels status --probe"
fi

# ---- Step 6: Optional git init ----
echo ""
echo "── Git Tracking ──"
if $GIT_INIT; then
  if [ -d "$OPENCLAW_DIR/.git" ]; then
    echo "ℹ️  ~/.openclaw is already a git repo."
  else
    if $APPLY; then
      cd "$OPENCLAW_DIR"
      git init
      if [ -f "$REPO_DIR/.gitignore" ]; then
        cp "$REPO_DIR/openclaw/.gitignore" "$OPENCLAW_DIR/.gitignore"
      fi
      git add -A
      git commit -m "Initial OpenClaw config snapshot" 2>/dev/null || echo "  ℹ️  Nothing to commit yet."
      echo "✅  Git repo initialized at $OPENCLAW_DIR"
    else
      echo "📋  Would git init $OPENCLAW_DIR"
    fi
  fi
fi

echo ""
echo "============================================"
echo " Setup Complete!"
echo "============================================"
