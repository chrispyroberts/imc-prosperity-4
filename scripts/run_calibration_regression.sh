#!/usr/bin/env bash
# runs every round 1 validator with quote-match gate. fails fast on any failure.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f "calibration/round1/osmium/bots.json" ]; then
    echo "skip: calibration artifacts not present. run emit_config first."
    exit 0
fi

export PYTHONPATH="${PWD}"
PYTHON="backtester/.venv/bin/python"

echo "== running round1 calibration regression with 95% gate =="
echo ""

failed=0

echo "osmium bot1"
if $PYTHON -m calibration.round1.osmium.scripts.validate_bot1 --gate 0.95 > /tmp/osmium_bot1.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL"
    failed=1
    tail -5 /tmp/osmium_bot1.out
fi
echo ""

echo "osmium bot2"
if $PYTHON -m calibration.round1.osmium.scripts.validate_bot2 --gate 0.95 > /tmp/osmium_bot2.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL"
    failed=1
    tail -5 /tmp/osmium_bot2.out
fi
echo ""

echo "osmium bot3"
if $PYTHON -m calibration.round1.osmium.scripts.validate_bot3 > /tmp/osmium_bot3.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL (bot3 is informational only)"
    tail -10 /tmp/osmium_bot3.out
fi
echo ""

echo "pepper bot1"
if $PYTHON -m calibration.round1.pepper.scripts.validate_bot1 --gate 0.95 > /tmp/pepper_bot1.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL"
    failed=1
    tail -5 /tmp/pepper_bot1.out
fi
echo ""

echo "pepper bot2"
if $PYTHON -m calibration.round1.pepper.scripts.validate_bot2 --gate 0.95 > /tmp/pepper_bot2.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL"
    failed=1
    tail -5 /tmp/pepper_bot2.out
fi
echo ""

echo "pepper bot3"
if $PYTHON -m calibration.round1.pepper.scripts.validate_bot3 > /tmp/pepper_bot3.out 2>&1; then
    echo "  PASS"
else
    echo "  FAIL (bot3 is informational only)"
    tail -10 /tmp/pepper_bot3.out
fi
echo ""

if [ $failed -eq 0 ]; then
    echo "== all validators passed =="
    exit 0
else
    echo "== some validators failed (see details above) =="
    exit 1
fi
