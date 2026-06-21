#!/bin/sh
set -eu

MODE="${AI_SCOUT_MODE:-dry_run}"
COMMAND="${AI_SCOUT_COMMAND:-ai-scout}"
CONFIG_DIR="${AI_SCOUT_CONFIG_DIR:-/host-config}"
DATA_DIR="${AI_SCOUT_DATA_DIR:-/data}"

if [ "$MODE" = "dry-run" ]; then
  MODE="dry_run"
fi

case "$MODE" in
  observe|dry_run|assist|autonomous)
    ;;
  *)
    echo "Invalid AI_SCOUT_MODE: $MODE" >&2
    echo "Allowed values: observe, dry_run, assist, autonomous" >&2
    exit 64
    ;;
esac

if [ "$MODE" = "autonomous" ]; then
  if [ "${AI_SCOUT_AUTONOMOUS_CONFIRM:-}" != "I_UNDERSTAND_AUTONOMOUS_SIDE_EFFECTS" ]; then
    echo "Autonomous mode requires AI_SCOUT_AUTONOMOUS_CONFIRM=I_UNDERSTAND_AUTONOMOUS_SIDE_EFFECTS" >&2
    exit 78
  fi
fi

mkdir -p "$DATA_DIR/memory" "$DATA_DIR/reports" "$DATA_DIR/runs"

if command -v "$COMMAND" >/dev/null 2>&1; then
  exec "$COMMAND" run \
    --mode "$MODE" \
    --config-dir "$CONFIG_DIR" \
    --data-dir "$DATA_DIR"
fi

echo "AI Scout CLI command not found: $COMMAND" >&2
echo "Install the project package or set AI_SCOUT_COMMAND to the executable path." >&2
exit 64
