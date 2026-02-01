---
description: How to run the main trading system orchestrator
---

# Run Trading System

This workflow starts the main trading system which orchestrates all active agents.

1. Activate the environment (if not already active):

   ```bash
   conda activate tflow
   ```

2. Run the main orchestrator:

   ```bash
   python MoondevRED/_engine/main.py
   ```

   // turbo
   3. This will start the `main.py` script which loads `ACTIVE_AGENTS` from `main.py` and `config.py` in `_engine/01_foundation`.

3. Monitor the output in the terminal. The system runs in a loop with a sleep interval defined in `config.py`.

4. To stop, press `Ctrl+C`.
