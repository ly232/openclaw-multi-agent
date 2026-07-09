#!/bin/bash
# =============================================================================
# Multi-Agent Config Merger
# =============================================================================
# Automatically merges the multi-agent configuration into your existing
# ~/.openclaw/openclaw.json.
#
# If no conflicts are found, it performs the merge automatically.
# If a conflict is found (section already exists), it shows the diff and
# asks you to resolve manually.
#
# Usage:
#   ./openclaw/merge-config.sh                    # preview mode (dry-run)
#   ./openclaw/merge-config.sh --apply            # actually merge
#   ./openclaw/merge-config.sh --help             # show help
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/openclaw.json.template"
EXISTING="$HOME/.openclaw/openclaw.json"
BACKUP="$HOME/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"
APPLY=false
FORCE=false

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --force) APPLY=true; FORCE=true ;;
    --help|-h)
      echo "Usage: $0 [--apply] [--force]"
      echo "  --apply    Apply the merge (default: dry-run preview)"
      echo "  --force    Skip conflict checks and force-apply the merge"
      exit 0 ;;
  esac
done

# Check prerequisites
if [ ! -f "$EXISTING" ]; then
  echo "❌  No existing config found at $EXISTING"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "❌  jq is required. Install it: brew install jq"
  exit 1
fi

# ---- Strip JSON5 comments to get valid JSON ----
# Only removes // when it has whitespace before it
# (avoids breaking URLs like https://...)
strip_json5() {
  sed -E \
    -e 's|^[[:space:]]*//.*$||g' \
    -e 's|[[:space:]]+//.*$||g' \
    "$1" | \
  sed -E 's|,[[:space:]]*([}\]])|\1|g' | \
  sed -E '/^[[:space:]]*$/d'
}

echo "============================================"
echo " Multi-Agent Config Merger"
echo "============================================"
echo ""

# Parse existing config (strip JSON5)
EXISTING_CLEAN=$(strip_json5 "$EXISTING")
GENERATED_RAW=$("$SCRIPT_DIR/generate-config.sh")

# Write generated config to temp file
GENERATED_TMP=$(mktemp)
echo "$GENERATED_RAW" > "$GENERATED_TMP"
GENERATED_CLEAN=$(strip_json5 "$GENERATED_TMP")
rm "$GENERATED_TMP"

# Write clean versions to temp files for jq
EXISTING_TMP=$(mktemp)
GENERATED_TMP2=$(mktemp)
echo "$EXISTING_CLEAN" > "$EXISTING_TMP"
echo "$GENERATED_CLEAN" > "$GENERATED_TMP2"

# Validate both parse as valid JSON
if ! jq '.' "$EXISTING_TMP" >/dev/null 2>&1; then
  echo "❌  Existing config has invalid JSON after stripping comments."
  echo "   Falling back to manual merge."
  echo ""
  echo "To resolve manually:"
  echo "  1. Generate the new config:  $SCRIPT_DIR/generate-config.sh"
  echo "  2. Merge agents.list, bindings, and tools.agentToAgent into:"
  echo "     $EXISTING"
  echo "  3. Restart:  openclaw gateway restart"
  rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
  exit 1
fi
if ! jq '.' "$GENERATED_TMP2" >/dev/null 2>&1; then
  echo "❌  Generated config has invalid JSON. Check the template."
  rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
  exit 1
fi

# ---- Check for conflicts ----
CONFLICTS=()

if jq -e '.agents.list' "$EXISTING_TMP" >/dev/null 2>&1; then
  CONFLICTS+=("agents.list already exists in your config")
fi

if jq -e '.bindings' "$EXISTING_TMP" >/dev/null 2>&1; then
  CONFLICTS+=("bindings already exists in your config")
fi

if jq -e '.tools.agentToAgent' "$EXISTING_TMP" >/dev/null 2>&1; then
  CONFLICTS+=("tools.agentToAgent already exists in your config")
fi

if [ ${#CONFLICTS[@]} -gt 0 ]; then
  if $FORCE; then
    echo "⚠️  Conflicts detected but --force specified. Overwriting anyway."
    for c in "${CONFLICTS[@]}"; do
      echo "   • $c"
    done
    echo ""
  else
    echo "⚠️  Merge conflicts detected:"
    for c in "${CONFLICTS[@]}"; do
      echo "   • $c"
    done
    echo ""
    echo "These sections already exist in your config. Automatic merge aborted."
    echo ""
    echo "Options:"
    echo "  • Use --force to overwrite anyway"
    echo "  • Or resolve manually:"
    echo ""
    echo "    1. Review what would be added:"
    echo "       $SCRIPT_DIR/generate-config.sh"
    echo ""
    echo "    2. Manually merge the relevant sections into:"
    echo "       $EXISTING"
    echo ""
    echo "    3. Restart the gateway:"
    echo "       openclaw gateway restart"
    rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
    exit 1
  fi
fi

echo "✅  No conflicts detected."
echo ""

# ---- Perform the merge ----
if ! $APPLY; then
  echo "Dry-run mode. Run with --apply to perform the merge."
  echo ""
  echo "Changes to be made:"
  echo "  1. Add agents.list (4 specialist agents)"
  echo "  2. Add bindings (WeChat → orchestrator)"
  echo "  3. Add tools.agentToAgent.enabled: true"
  echo ""
  echo "Backup will be created at: $BACKUP"
  rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
  exit 0
fi

echo "Merging..."

# Build the merge using jq
NEW_CONFIG=$(jq -s '
  .[0] as $existing |
  .[1] as $new |

  # Add agents.list
  if $existing.agents then
    $existing | .agents.list = $new.agents.list
  else
    $existing | .agents = $new.agents
  end |

  # Add bindings
  .bindings = $new.bindings |

  # Add tools.agentToAgent (merge into existing tools)
  if .tools then
    .tools.agentToAgent = $new.tools.agentToAgent
  else
    .tools = $new.tools
  end
' "$EXISTING_TMP" "$GENERATED_TMP2")

# Validate the result
if echo "$NEW_CONFIG" | jq '.' >/dev/null 2>&1; then
  # Create backup
  cp "$EXISTING" "$BACKUP"
  echo "✅  Backup created at $BACKUP"

  # Write merged config
  echo "$NEW_CONFIG" > "$EXISTING"
  echo "✅  Config merged into $EXISTING"
  echo ""
  echo "Restart the gateway to apply:"
  echo ""
  echo "    openclaw gateway restart"
  echo ""
  echo "Verify:"
  echo ""
  echo "    openclaw agents list --bindings"
else
  echo "❌  Merge produced invalid JSON. Aborting."
  echo "   Your original config is preserved at $EXISTING"
  echo "   Backup saved at $BACKUP"
  rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
  exit 1
fi

rm -f "$EXISTING_TMP" "$GENERATED_TMP2"
