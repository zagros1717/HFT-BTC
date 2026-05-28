#!/bin/bash
# Daily pipeline runner for BTC research machine
# Runs the full pipeline (replay -> features -> labels -> train -> backtest -> report)
# for yesterday's data

set -e

YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
EXCHANGE="bitfinex"
SYMBOL="BTCUSD"
HORIZON=5

echo "Running pipeline for $YESTERDAY..."
python main.py pipeline \
  --exchange "$EXCHANGE" \
  --symbol "$SYMBOL" \
  --start "$YESTERDAY" \
  --end "$YESTERDAY" \
  --horizon "$HORIZON"

echo "Pipeline complete for $YESTERDAY"

