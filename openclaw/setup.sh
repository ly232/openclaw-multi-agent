#!/bin/bash
# =============================================================================
# OpenClaw Multi-Agent Setup Script
# =============================================================================
# Safely deploys the multi-agent configuration to ~/.openclaw
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh              # preview mode (dry run)
#   ./setup.sh --apply      # actually deploy
#   ./setup.sh --git-init   # also git init ~/.openclaw for version tracking
# =============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCLAW_DIR="$HOME/.openclaw"
APPLY=false
GIT_INIT=false

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --git-init) GIT_INIT=true ;;
    --help|-h)
      echo "Usage: $0 [--apply] [--git-init]"
      echo ""
      echo "  --apply      Actually copy files (default: dry-run preview)"
      echo "  --git-init   Also 'git init ~/.openclaw' for version tracking"
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
if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "⚠️  ~/.openclaw not found. Have you run 'openclaw setup' yet?"
  echo "   Run 'openclaw setup' first, then run this script."
  exit 1
fi

if [ ! -f "$OPENCLAW_DIR/openclaw.json" ]; then
  echo "⚠️  ~/.openclaw/openclaw.json not found. Cannot merge config."
  exit 1
fi

# ---- Step 1: Back up existing config ----
BACKUP="$OPENCLAW_DIR/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"
if $APPLY; then
  cp "$OPENCLAW_DIR/openclaw.json" "$BACKUP"
  echo "✅  Backed up config → $BACKUP"
else
  echo "📋  Would backup config → $BACKUP"
fi

# ---- Step 2: Create workspace directories ----
WORKSPACES=("orchestrator" "coding" "research" "cs285" "general")
for ws in "${WORKSPACES[@]}"; do
  TARGET="$OPENCLAW_DIR/workspaces/$ws"
  SOURCE="$REPO_DIR/openclaw/workspaces/$ws"
  if $APPLY; then
    mkdir -p "$TARGET"
    # Copy all tracked workspace files (identity, instructions, skills)
    cp -R "$SOURCE/"* "$TARGET/" 2>/dev/null || true
    # If USER.md doesn't exist at destination, create from example template
    if [ ! -f "$TARGET/USER.md" ] && [ -f "$SOURCE/USER.md.example" ]; then
      cp "$SOURCE/USER.md.example" "$TARGET/USER.md"
      echo "  📝 Created USER.md from template (edit with your details)"
    fi
    echo "✅  Workspace '$ws' → $TARGET"
  else
    echo "📋  Would copy workspace '$ws': $SOURCE/ → $TARGET/"
  fi
done

# ---- Step 3: Create agent directories ----
for agent in "${WORKSPACES[@]}"; do
  TARGET="$OPENCLAW_DIR/agents/$agent/agent"
  if $APPLY; then
    mkdir -p "$TARGET"
    echo "✅  Agent dir '$agent' → $TARGET"
  else
    echo "📋  Would create agent dir '$agent' → $TARGET"
  fi
done

# ---- Step 4: Config merge instructions ----
echo ""
echo "============================================"
echo " Config Merge Required"
echo "============================================"
echo ""
echo "Run the auto-merger to add multi-agent config:"
echo ""
echo "    $REPO_DIR/openclaw/merge-config.sh --apply"
echo ""
echo "It will check for conflicts and merge automatically."
echo "Or preview first:"
echo ""
echo "    $REPO_DIR/openclaw/merge-config.sh"
echo ""

# ---- Step 5: Restart gateway ----
if $APPLY; then
  echo ""
  echo "============================================"
  echo " Gateway Restart"
  echo "============================================"
  echo ""
  echo "After merging config, restart the gateway:"
  echo ""
  echo "    openclaw gateway restart"
  echo ""
  echo "Then verify:"
  echo ""
  echo "    openclaw agents list --bindings"
  echo "    openclaw channels status --probe"
  echo ""
fi

# ---- Step 6: Optional git init ----
if $GIT_INIT; then
  if [ -d "$OPENCLAW_DIR/.git" ]; then
    echo "ℹ️  ~/.openclaw is already a git repo."
  else
    if $APPLY; then
      cd "$OPENCLAW_DIR"
      git init
      cp "$REPO_DIR/openclaw/.gitignore" "$OPENCLAW_DIR/.gitignore"
      git add -A
      git commit -m "Initial OpenClaw config snapshot"
      echo "✅  Git repo initialized at $OPENCLAW_DIR"
    else
      echo "📋  Would git init $OPENCLAW_DIR (skip with --apply)"
    fi
  fi
fi

echo ""
echo "Done!"
