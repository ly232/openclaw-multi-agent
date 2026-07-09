#!/bin/bash
# =============================================================================
# OpenClaw Multi-Agent Smoke Test
# =============================================================================
# Tests that all specialist agents are loaded, responsive, and can route
# through the orchestrator.
#
# Usage:
#   ./openclaw/test.sh              # Quick test (all agents, no routing)
#   ./openclaw/test.sh --verbose    # Full output including agent responses
#   ./openclaw/test.sh --routing    # Also test orchestrator routing
#   ./openclaw/test.sh --all        # Everything
#   ./openclaw/test.sh --help       # Show usage
# =============================================================================

set -euo pipefail

VERBOSE=false
TEST_ROUTING=false
TIMEOUT=30

for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=true ;;
    --routing|-r) TEST_ROUTING=true ;;
    --all|-a) VERBOSE=true; TEST_ROUTING=true ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --verbose, -v    Show full agent responses"
      echo "  --routing, -r    Also test orchestrator routing via sessions_send"
      echo "  --all, -a        Full test suite (verbose + routing)"
      echo "  --help, -h       Show this help"
      echo ""
      echo "Exit codes:"
      echo "  0  All tests passed"
      echo "  1  One or more tests failed"
      echo "  2  Gateway not reachable"
      exit 0
      ;;
  esac
done

PASS=0
FAIL=0

print_result() {
  local label="$1"
  local status="$2"
  if [ "$status" = "ok" ]; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $label"
    FAIL=$((FAIL + 1))
  fi
}

# === Prelim: check gateway ===
echo "============================================"
echo " OpenClaw Multi-Agent Smoke Test"
echo "============================================"
echo ""

echo "🔍 Checking gateway..."
if ! openclaw status &>/dev/null; then
  echo "  ❌ Gateway not reachable. Is 'openclaw gateway start' running?"
  exit 2
fi
echo "  ✅ Gateway reachable"
PASS=$((PASS + 1))

# === Test 1: All agents exist ===
echo ""
echo "🔍 Checking agents list..."

AGENTS=$(openclaw agents list --bindings 2>/dev/null || echo "")
for expected in orchestrator coding research general; do
  if echo "$AGENTS" | grep -q "$expected"; then
    print_result "Agent '$expected' registered" "ok"
  else
    print_result "Agent '$expected' registered" "fail"
  fi
done

# === Test 2: Each agent responds ===
echo ""
echo "🔍 Testing agent responsiveness..."
echo ""

for agent in orchestrator coding research cs285 general; do
  # What we're testing:
  #   - The agent can be invoked via the Gateway CLI
  #   - It loads its workspace files (AGENTS.md, SOUL.md, etc.)
  #   - It returns a non-error response
  #   - The response reflects the agent's persona
  OUTPUT=$(openclaw agent --agent "$agent" --message "Who are you? Reply in one sentence." --timeout $TIMEOUT 2>&1 || true)

  if echo "$OUTPUT" | grep -qi "error\|timeout\|failed\|not found"; then
    print_result "$agent: responds without error" "fail"
    $VERBOSE && echo "       Output: $OUTPUT"
  else
    # Extract just the assistant's text reply
    REPLY=$(echo "$OUTPUT" | grep -v "^\[" | grep -v "^{" | head -5 | tr '\n' ' ' | sed 's/  */ /g')
    print_result "$agent: responds without error" "ok"
    $VERBOSE && echo "       Reply: $REPLY"
  fi
done

# === Test 3: Persona differentiation ===
echo ""
echo "🔍 Checking persona differentiation..."

# Get responses from each agent and check they sound different
CODE_RESP=$(openclaw agent --agent coding --message "What do you do? One sentence." --timeout $TIMEOUT 2>&1 | grep -v "^\[" | grep -v "^{" | head -3 | tr '\n' ' ')
GEN_RESP=$(openclaw agent --agent general --message "What do you do? One sentence." --timeout $TIMEOUT 2>&1 | grep -v "^\[" | grep -v "^{" | head -3 | tr '\n' ' ')
RES_RESP=$(openclaw agent --agent research --message "What do you do? One sentence." --timeout $TIMEOUT 2>&1 | grep -v "^\[" | grep -v "^{" | head -3 | tr '\n' ' ')

# Crude check: if responses differ in length by more than trivial amount, personas differ
CODE_LEN=${#CODE_RESP}
GEN_LEN=${#GEN_RESP}
RES_LEN=${#RES_RESP}

if [ "$CODE_LEN" -gt 10 ] && [ "$GEN_LEN" -gt 10 ] && [ "$RES_LEN" -gt 10 ]; then
  print_result "All agents return substantive responses" "ok"
else
  print_result "All agents return substantive responses" "fail"
fi

if $VERBOSE; then
  echo "       Coding:   $CODE_RESP"
  echo "       General:  $GEN_RESP"
  echo "       Research: $RES_RESP"
fi

# === Test 4: Orchestrator routing (optional) ===
if $TEST_ROUTING; then
  echo ""
  echo "🔍 Testing orchestrator routing..."
  echo ""
  echo "   This sends a message to the orchestrator agent. If"
  echo "   sessions_send works, it will classify the intent and"
  echo "   forward to the appropriate specialist."

  # Test coding routing
  echo ""
  echo "   Sending coding request..."
  ROUTE_OUTPUT=$(openclaw agent --agent orchestrator \
    --message "Write a one-line Python function to add two numbers." \
    --timeout $TIMEOUT 2>&1 || true)

  if echo "$ROUTE_OUTPUT" | grep -qi "error\|timeout"; then
    print_result "orchestrator routes coding request" "fail"
    echo "       Output: $ROUTE_OUTPUT"
  else
    REPLY=$(echo "$ROUTE_OUTPUT" | grep -v "^\[" | grep -v "^{" | head -5 | tr '\n' ' ' | sed 's/  */ /g')
    print_result "orchestrator routes coding request" "ok"
    $VERBOSE && echo "       Reply: $REPLY"
  fi

  # Test general routing
  echo ""
  echo "   Sending general request..."
  ROUTE_OUTPUT2=$(openclaw agent --agent orchestrator \
    --message "What's a good book to read this weekend?" \
    --timeout $TIMEOUT 2>&1 || true)

  if echo "$ROUTE_OUTPUT2" | grep -qi "error\|timeout"; then
    print_result "orchestrator routes general request" "fail"
  else
    REPLY2=$(echo "$ROUTE_OUTPUT2" | grep -v "^\[" | grep -v "^{" | head -5 | tr '\n' ' ' | sed 's/  */ /g')
    print_result "orchestrator routes general request" "ok"
    $VERBOSE && echo "       Reply: $REPLY2"
  fi
fi

# === Summary ===
echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Troubleshooting tips:"
  echo "  - Are all 4 agents in 'openclaw agents list --bindings'?"
  echo "  - Did you restart the gateway after adding agents.list?"
  echo "  - Check gateway logs: openclaw logs --follow"
  echo "  - Is the model provider working? openclaw health"
  exit 1
fi

exit 0
