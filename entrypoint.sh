#!/bin/bash
RETRY_DELAY=5
MAX_DELAY=120
MAX_RETRIES=10
RETRY_COUNT=0

while true; do
    python bot.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Max retries ($MAX_RETRIES) reached. Exiting."
        exit $EXIT_CODE
    fi
    echo "Bot exited with code $EXIT_CODE (retry $RETRY_COUNT/$MAX_RETRIES). Waiting ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
    if [ $RETRY_DELAY -gt $MAX_DELAY ]; then
        RETRY_DELAY=$MAX_DELAY
    fi
done
