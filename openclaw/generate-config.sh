#!/bin/bash
# =============================================================================
# OpenClaw Multi-Agent Config Generator
# =============================================================================
# Reads openclaw.json.template and replaces {{HOME}} with your home directory.
#
# Usage:
#   ./openclaw/generate-config.sh                          # print to stdout
#   ./openclaw/generate-config.sh > ~/.openclaw/openclaw.json.new   # save to file
#   ./openclaw/generate-config.sh --diff                    # show diff vs existing
#   ./openclaw/generate-config.sh --help                    # show help
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/openclaw.json.template"
EXISTING="$HOME/.openclaw/openclaw.json"
MODE="stdout"

for arg in "$@"; do
  case "$arg" in
    --diff|-d) MODE="diff" ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  (none)       Print generated config to stdout"
      echo "  --diff, -d   Show diff between generated and existing config"
      echo "  --help, -h   Show this help"
      echo ""
      echo "Examples:"
      echo "  $0                                  # preview generated config"
      echo "  $0 > /tmp/new.json                  # save to file for manual merge"
      echo "  $0 --diff                            # see what would change"
      echo "  cp \$($0) ~/.openclaw/openclaw.json   # ⚠️  overwrites existing config"
      exit 0
      ;;
  esac
done

if [ ! -f "$TEMPLATE" ]; then
  echo "Error: Template not found at $TEMPLATE"
  exit 1
fi

# Generate config by substituting {{HOME}}
GENERATED=$(sed "s|{{HOME}}|$HOME|g" "$TEMPLATE")

case "$MODE" in
  stdout)
    echo "$GENERATED"
    ;;
  diff)
    if [ ! -f "$EXISTING" ]; then
      echo "No existing config at $EXISTING."
      echo "Generated config would be written fresh:"
      echo ""
      echo "$GENERATED"
    else
      echo "--- Existing: $EXISTING"
      echo "+++ Generated from template"
      echo ""
      diff -u "$EXISTING" <(echo "$GENERATED") || true
    fi
    ;;
esac
