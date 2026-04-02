# prosperity4mcbt package

This directory contains the installable Python package for the repo.

It ships two CLIs:

- `prosperity4mcbt`
  Rust-backed Monte Carlo backtester for Prosperity 4 tutorial-round strategies.
- `prosperity3bt`
  Legacy CSV replay CLI kept for historical playback and compatibility.

## Install

```bash
uv venv
uv sync
source .venv/bin/activate
uv pip install -e .
```

## Monte Carlo

Quick run:

```bash
prosperity4mcbt ../example_trader.py --quick --out ../tmp/example/dashboard.json
```

Default heavy run:

```bash
prosperity4mcbt ../example_trader.py --out ../tmp/example/dashboard.json
```

Open the dashboard locally:

```bash
prosperity4mcbt ../example_trader.py --quick --vis --out ../tmp/example/dashboard.json
```

## Replay

Replay the tutorial CSVs directly:

```bash
prosperity3bt ../example_trader.py 0 --data ../data
```

The bundled frontend in this repo is Monte Carlo-only, so `prosperity3bt --vis` is not supported by the shipped UI.

## Notes

- `prosperity4mcbt` works with normal Prosperity-style `Trader.run(state)` files.
- No special visualizer logger is required for Monte Carlo mode.
- Tutorial-round Monte Carlo currently provides empty observations and does not simulate conversions.
