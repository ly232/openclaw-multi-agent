#!/bin/bash
# =============================================================================
# Multi-Agent Config Merger
# =============================================================================
# Merges the multi-agent configuration (agents.list, bindings, tools) into
# your existing ~/.openclaw/openclaw.json while preserving all existing
# settings (gateway, auth, models, plugins, channels, etc.).
#
# Usage:
#   ./openclaw/merge-config.sh                    # preview mode (dry-run)
#   ./openclaw/merge-config.sh --apply            # actually merge
#   ./openclaw/merge-config.sh --help             # show help
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
  echo "    Run 'openclaw onboard' or 'openclaw setup' first."
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "❌  jq is required. Install it: brew install jq"
  exit 1
fi

# =============================================================================
# Strip JSON5 comments to get valid JSON
# =============================================================================
# Works on a FILE path ($1), outputs clean JSON to stdout.
# Handles: trailing commas, // comments on their own line, // after values.
strip_json5() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo ""
    return
  fi

  # Phase 1: strip // comments — safe delimiter (not /) avoids sed escaping
  sed -E \
    -e 's|^[[:space:]]*//.*$||' \
    -e 's|[[:space:]]+//[[:space:]].*$||' \
    -e 's|[[:space:]]+//[a-zA-Z].*$||' \
    "$file" |

  # Phase 2: remove trailing commas before } or ] (multi-pass for nesting)
  sed -E 's|,[[:space:]]*([\}\]])|\1|g' |
  sed -E 's|,[[:space:]]*([\}\]])|\1|g' |

  # Phase 3: drop blank lines
  sed -E '/^[[:space:]]*$/d'
}

# =============================================================================
# Better approach: use jq to merge multi-agent sections into existing config
# =============================================================================
# Instead of stripping JSON5 and parsing with jq (which loses the // comments),
# we now:
#   1. Use generate-config.sh to produce the multi-agent sections
#   2. Use jq to surgically merge those sections into the existing config
#   3. Preserve EVERYTHING in the existing config (including // comments)
#
# The existing config's // comments are its own business — we only touch
# specific top-level keys: agents.list, bindings, tools.agentToAgent.

# =============================================================================
# Generate the new multi-agent sections
# =============================================================================
echo "============================================"
echo " Multi-Agent Config Merger"
echo "============================================"
echo ""

# Get the generated config (with HOME substituted but no API keys needed here)
GENERATED_RAW=$("$SCRIPT_DIR/generate-config.sh" 2>/dev/null || echo "")

# Extract just the JSON part (before the // per-agent summary)
GENERATED_JSON=$(echo "$GENERATED_RAW" | sed '/^\/\/ ── Per-agent/q' | head -n -1)

if [ -z "$GENERATED_JSON" ]; then
  echo "❌  Failed to generate config. Check the template."
  exit 1
fi

# Write to temp file for jq
GENERATED_TMP=$(mktemp)
echo "$GENERATED_JSON" > "$GENERATED_TMP"

# =============================================================================
# Check for conflicts
# =============================================================================
# We don't need to parse existing config for this — just check if sections exist
CONFLICTS=()

# Use grep on the raw file (with JSON5 comments)
if grep -q '"agents"[[:space:]]*:[[:space:]]*{' "$EXISTING" 2>/dev/null && \
   grep -q '"list"[[:space:]]*:' "$EXISTING" 2>/dev/null; then
  CONFLICTS+=("agents.list already exists in your config")
fi

if grep -q '"bindings"[[:space:]]*:' "$EXISTING" 2>/dev/null; then
  CONFLICTS+=("bindings already exists in your config")
fi

# Check tools.agentToAgent more carefully (it might exist in the file)
if grep -q '"agentToAgent"' "$EXISTING" 2>/dev/null; then
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
    echo ""
    echo "Options:"
    echo "  • Use --force to overwrite anyway"
    echo "  • Or check what would change:"
    echo "       diff <(jq . $EXISTING) <($SCRIPT_DIR/generate-config.sh | sed '/^\/\/ ── Per-agent/q' | head -n -1 | jq .)"
    echo ""
    echo "  • Or just regenerate the full config (preserving your secrets):"
    echo "       $SCRIPT_DIR/generate-config.sh --output"
    echo ""
    echo "    This writes a COMPLETE new config — including your gateway,"
    echo "    auth, and model settings extracted from your existing config."
    rm -f "$GENERATED_TMP"
    exit 1
  fi
fi

echo "✅  No conflicts detected."
echo ""

# =============================================================================
# Perform the merge using jq
# =============================================================================
if ! $APPLY; then
  echo "Dry-run mode. Run with --apply to perform the merge."
  echo ""
  echo "Changes to be made to $EXISTING:"
  echo "  1. Set agents.list (multi-agent definitions)"
  echo "  2. Set bindings (WeChat → orchestrator)"
  echo "  3. Set tools.agentToAgent.enabled: true"
  echo ""
  echo "Backup will be created at: $BACKUP"
  echo ""
  echo "All existing settings (gateway, auth, models, plugins, channels)"
  echo "will be preserved."
  rm -f "$GENERATED_TMP"
  exit 0
fi

echo "Merging..."

# Build the merge using jq with surgical key-by-key approach
# We write a small jq program that only touches the 3 specific keys
NEW_CONFIG=$(jq -s --argjson sections "$(jq '{agents: {list: .agents.list}, bindings: .bindings, tools: {agentToAgent: .tools.agentToAgent}}' "$GENERATED_TMP")" '
  .[0] as $existing |
  $sections as $new |

  # Start with existing config, then overlay only our sections
  $existing |

  # Set agents.list (preserving agents.defaults)
  if .agents then
    .agents.list = $new.agents.list
  else
    .agents = { list: $new.agents.list }
  end |

  # Set bindings
  .bindings = $new.bindings |

  # Set tools.agentToAgent (preserving everything else in tools)
  if .tools then
    .tools.agentToAgent = $new.tools.agentToAgent
  else
    .tools = $new.tools
  end
' "$EXISTING" 2>/dev/null) || {
  # Fallback: if jq can't parse the existing JSON5 directly, try the stripped version
  echo "⚠️  Existing config has JSON5 comments. Using stripped version for jq..."

  # Strip JSON5 to get valid JSON for jq processing
  EXISTING_CLEAN=$(strip_json5 "$EXISTING")
  EXISTING_TMP=$(mktemp)
  echo "$EXISTING_CLEAN" > "$EXISTING_TMP"

  SECTIONS=$(jq '{agents: {list: .agents.list}, bindings: .bindings, tools: {agentToAgent: .tools.agentToAgent}}' "$GENERATED_TMP")

  NEW_CONFIG=$(jq -s --argjson sections "$SECTIONS" '
    .[0] as $existing |
    $sections as $new |

    $existing |

    if .agents then
      .agents.list = $new.agents.list
    else
      .agents = { list: $new.agents.list }
    end |

    .bindings = $new.bindings |

    if .tools then
      .tools.agentToAgent = $new.tools.agentToAgent
    else
      .tools = $new.tools
    end
  ' "$EXISTING_TMP" 2>/dev/null) || {
    echo "❌  Merge produced invalid JSON. Aborting."
    echo "   Your original config is preserved at $EXISTING"
    rm -f "$GENERATED_TMP" "$EXISTING_TMP"
    exit 1
  }

  # Convert back to JSON5 with comments by preserving the original as base
  # Actually, we lose comments — so warn the user
  echo "   ⚠️  Note: JSON5 comments in your existing config will be lost."
  echo "   (The JSON structure itself is preserved, but // comments are stripped.)"

  rm -f "$EXISTING_TMP"
}

# Validate the result
if echo "$NEW_CONFIG" | jq '.' >/dev/null 2>&1; then
  # Create backup
  cp "$EXISTING" "$BACKUP"
  echo "✅  Backup created at $BACKUP"

  # Write merged config
  echo "$NEW_CONFIG" > "$EXISTING"
  echo "✅  Config merged into $EXISTING"
  echo ""
  echo "Next steps:"
  echo ""
  echo "  1. Restart the gateway:"
  echo "       openclaw gateway restart"
  echo ""
  echo "  2. Verify:"
  echo "       openclaw agents list"
  echo "       openclaw channels status"
  echo ""
  echo "  3. (Optional) Generate per-agent models.json:"
  echo "       $SCRIPT_DIR/generate-config.sh --output"
  echo "     (This writes models.json for all agents with your API key.)"
else
  echo "❌  Merge produced invalid JSON. Aborting."
  echo "   Your original config is preserved at $EXISTING"
  echo "   Backup saved at $BACKUP"
  rm -f "$GENERATED_TMP"
  exit 1
fi

rm -f "$GENERATED_TMP"
