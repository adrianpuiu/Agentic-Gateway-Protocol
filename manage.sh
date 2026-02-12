#!/bin/bash

# AGP Gateway Management Script

CONFIG_DIR="$HOME/.agp"
LOG_FILE="$CONFIG_DIR/gateway.log"
PID_FILE="$CONFIG_DIR/gateway.pid"
VENV_PATH="$(pwd)/venv"
AGP_BIN="$VENV_PATH/bin/agp"

# Ensure config dir exists
mkdir -p "$CONFIG_DIR"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
}

start() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "AGP Gateway is already running (PID: $(cat "$PID_FILE"))."
        return
    fi

    echo "Starting AGP Gateway..."
    nohup "$AGP_BIN" gateway > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "AGP Gateway started with PID $!."
    echo "Logs are being written to $LOG_FILE"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "AGP Gateway is not running (no PID file)."
        return
    fi

    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping AGP Gateway (PID: $PID)..."
        kill "$PID"
        # Wait for it to actually stop
        for i in {1..5}; do
            if ! kill -0 "$PID" 2>/dev/null; then
                rm "$PID_FILE"
                echo "AGP Gateway stopped."
                return
            fi
            sleep 1
        done
        echo "Force killing AGP Gateway..."
        kill -9 "$PID"
        rm "$PID_FILE"
    else
        echo "AGP Gateway is not running (stale PID file removed)."
        rm "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "AGP Gateway is RUNNING (PID: $(cat "$PID_FILE"))."
        "$AGP_BIN" status
    else
        echo "AGP Gateway is STOPPED."
    fi
}

logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "Log file not found at $LOG_FILE"
        return
    fi
    tail -n 50 -f "$LOG_FILE"
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        usage
        ;;
esac
