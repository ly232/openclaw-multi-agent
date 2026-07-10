#!/bin/bash
# =============================================================================
# OpenClaw Multi-Agent Config Generator
# =============================================================================
# Reads openclaw.json.template and replaces placeholders with values from
# your local ~/.openclaw config (no sensitive data stored in the repo).
#
# Also generates per-agent models.json with your DeepSeek API key.
#
# Usage:
#   ./openclaw/generate-config.sh                          # print to stdout
#   ./openclaw/generate-config.sh --output                 # write to ~/.openclaw/openclaw.json
#   ./openclaw/generate-config.sh --diff                   # show diff vs existing
#   ./openclaw/generate-config.sh --help                   # show help
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/openclaw.json.template"
EXISTING="$HOME/.openclaw/openclaw.json"
MODE="stdout"

# ---------------------------------------------------------------------------
# Helper: safely read a value from an existing JSON config file
# ---------------------------------------------------------------------------
read_json_key() {
  local file="$1"
  local key="$2"
  if [ ! -f "$file" ]; then
    echo ""
    return
  fi
  # Strip JSON5 comments to get valid JSON
  local cleaned
  cleaned=$(sed -E \
    -e 's|^[[:space:]]*//.*$||g' \
    -e 's|[[:space:]]+//.*$||g' \
    "$file" | \
    sed -E 's|,[[:space:]]*([}\]])|\1|g' | \
    sed -E '/^[[:space:]]*$/d' 2>/dev/null || echo "")
  if [ -z "$cleaned" ]; then
    echo ""
    return
  fi
  if ! echo "$cleaned" | jq -e "$key" >/dev/null 2>&1; then
    echo ""
    return
  fi
  echo "$cleaned" | jq -r "$key"
}

# ---------------------------------------------------------------------------
# Helper: generate a random hex token
# ---------------------------------------------------------------------------
random_token() {
  openssl rand -hex 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(24))" 2>/dev/null || echo "insecure-token-change-me"
}

# ---------------------------------------------------------------------------
# Resolve all placeholders from local config / env / defaults
# ---------------------------------------------------------------------------
resolve_placeholders() {
  # HOME — always known
  HOME_VAL="$HOME"

  # GATEWAY_TOKEN — try existing config, else generate
  GATEWAY_TOKEN_VAL=$(read_json_key "$EXISTING" '.gateway.auth.token')
  if [ -z "$GATEWAY_TOKEN_VAL" ] || [ "$GATEWAY_TOKEN_VAL" = "null" ]; then
    GATEWAY_TOKEN_VAL=$(random_token)
  fi

  # DEEPSEEK_API_KEY — try various sources, never falls back to a real default
  DEEPSEEK_API_KEY=""
  # 1. Check existing orchestrator models.json
  if [ -f "$HOME/.openclaw/agents/orchestrator/agent/models.json" ]; then
    DEEPSEEK_API_KEY=$(read_json_key "$HOME/.openclaw/agents/orchestrator/agent/models.json" '.providers.deepseek.apiKey')
  fi
  # 2. Fall back to main agent models.json
  if [ -z "$DEEPSEEK_API_KEY" ] && [ -f "$HOME/.openclaw/agents/main/agent/models.json" ]; then
    DEEPSEEK_API_KEY=$(read_json_key "$HOME/.openclaw/agents/main/agent/models.json" '.providers.deepseek.apiKey')
  fi
  # 3. Fall back to environment variable
  if [ -z "$DEEPSEEK_API_KEY" ]; then
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
  fi
  # 4. Fall back to existing openclaw.json auth profiles
  if [ -z "$DEEPSEEK_API_KEY" ]; then
    DEEPSEEK_API_KEY=$(read_json_key "$EXISTING" '.auth.profiles["deepseek:default"].apiKey')
  fi
}

# ---------------------------------------------------------------------------
# Generate per-agent models.json with the DeepSeek API key
# ---------------------------------------------------------------------------
generate_agent_models() {
  local api_key="$1"
  local output_dir="$2"

  if [ -z "$api_key" ] || [ "$api_key" = "null" ]; then
    echo "  ⚠️  No DeepSeek API key found — models.json will have a placeholder."
    api_key="YOUR_DEEPSEEK_API_KEY"
  fi

  mkdir -p "$output_dir"

  cat > "$output_dir/models.json" << ENDJSON
{
  "providers": {
    "deepseek": {
      "baseUrl": "https://api.deepseek.com",
      "api": "openai-completions",
      "models": [
        {
          "id": "deepseek-v4-flash",
          "name": "DeepSeek V4 Flash",
          "reasoning": true,
          "input": ["text"],
          "cost": {
            "input": 0.14,
            "output": 0.28,
            "cacheRead": 0.028,
            "cacheWrite": 0
          },
          "contextWindow": 1000000,
          "maxTokens": 384000,
          "compat": {
            "supportsReasoningEffort": true,
            "supportsUsageInStreaming": true,
            "maxTokensField": "max_tokens"
          },
          "api": "openai-completions"
        },
        {
          "id": "deepseek-v4-pro",
          "name": "DeepSeek V4 Pro",
          "reasoning": true,
          "input": ["text"],
          "cost": {
            "input": 1.74,
            "output": 3.48,
            "cacheRead": 0.145,
            "cacheWrite": 0
          },
          "contextWindow": 1000000,
          "maxTokens": 384000,
          "compat": {
            "supportsReasoningEffort": true,
            "supportsUsageInStreaming": true,
            "maxTokensField": "max_tokens"
          },
          "api": "openai-completions"
        },
        {
          "id": "deepseek-chat",
          "name": "DeepSeek Chat",
          "reasoning": false,
          "input": ["text"],
          "cost": {
            "input": 0.28,
            "output": 0.42,
            "cacheRead": 0.028,
            "cacheWrite": 0
          },
          "contextWindow": 131072,
          "maxTokens": 8192,
          "compat": {
            "supportsUsageInStreaming": true,
            "maxTokensField": "max_tokens"
          },
          "api": "openai-completions"
        },
        {
          "id": "deepseek-reasoner",
          "name": "DeepSeek Reasoner",
          "reasoning": true,
          "input": ["text"],
          "cost": {
            "input": 0.28,
            "output": 0.42,
            "cacheRead": 0.028,
            "cacheWrite": 0
          },
          "contextWindow": 131072,
          "maxTokens": 65536,
          "compat": {
            "supportsReasoningEffort": false,
            "supportsUsageInStreaming": true,
            "maxTokensField": "max_tokens"
          },
          "api": "openai-completions"
        }
      ],
      "apiKey": "$api_key"
    }
  }
}
ENDJSON
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --output|-o) MODE="output" ;;
    --diff|-d)   MODE="diff" ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  (none)       Print generated config to stdout"
      echo "  --output, -o Write config AND per-agent models.json to ~/.openclaw/"
      echo "  --diff, -d   Show diff between generated and existing config"
      echo "  --help, -h   Show this help"
      echo ""
      echo "This script reads sensitive values (API keys, tokens) from your"
      echo "existing ~/.openclaw/ config — NOT from the repo."
      echo ""
      echo "No secrets are stored in this repository."
      exit 0
      ;;
  esac
done

if [ ! -f "$TEMPLATE" ]; then
  echo "Error: Template not found at $TEMPLATE"
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve placeholders from local config
# ---------------------------------------------------------------------------
resolve_placeholders

# ---------------------------------------------------------------------------
# Generate config by substituting all {{PLACEHOLDER}} in the template
# ---------------------------------------------------------------------------
GENERATED=$(cat "$TEMPLATE")
GENERATED=${GENERATED//"{{HOME}}"/$HOME_VAL}
GENERATED=${GENERATED//"{{GATEWAY_TOKEN}}"/$GATEWAY_TOKEN_VAL}
GENERATED=${GENERATED//"{{DEEPSEEK_API_KEY}}"/$DEEPSEEK_API_KEY}

case "$MODE" in
  stdout)
    echo "$GENERATED"
    echo ""
  # Print per-agent model summary
    AGENTS=("orchestrator" "coding" "research" "cs285" "general")
    echo "// ── Per-agent models.json ──"
    if [ -n "$DEEPSEEK_API_KEY" ] && [ "$DEEPSEEK_API_KEY" != "null" ]; then
      echo "// API key: found (${DEEPSEEK_API_KEY:0:8}…${DEEPSEEK_API_KEY: -4})"
    else
      echo "// ⚠️  API key not found. Set DEEPSEEK_API_KEY env var or run:"
      echo "//    export DEEPSEEK_API_KEY='sk-your-key-here'"
    fi
    echo "// Run with --output to write everything to ~/.openclaw/"
    ;;

  output)
    mkdir -p "$HOME/.openclaw"

    # Write main config
    echo "$GENERATED" > "$HOME/.openclaw/openclaw.json"
    echo "✅  Config written to $HOME/.openclaw/openclaw.json"

    # Write per-agent models.json
    AGENTS=("orchestrator" "coding" "research" "cs285" "general")
    for agent in "${AGENTS[@]}"; do
      AGENT_DIR="$HOME/.openclaw/agents/$agent/agent"
      mkdir -p "$AGENT_DIR"
      generate_agent_models "$DEEPSEEK_API_KEY" "$AGENT_DIR"
      echo "✅  models.json written to $AGENT_DIR/models.json"
    done
    ;;

  diff)
    if [ ! -f "$EXISTING" ]; then
      echo "No existing config at $EXISTING."
      echo "Generated config:"
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
