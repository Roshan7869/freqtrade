---
description: How to create a new agent in the correct operational hierarchy
---

# Create New Agent

This workflow guides you through creating a new agent within the MoondevRED operational hierarchy.

1. **Identify Agent Purpose**: determine the primary function of your agent.
   - Core/Foundation? -> `01_foundation`
   - Data collection? -> `02_data_acquisition`
   - Strategy/Research? -> `03_strategy_development`
   - Backtesting? -> `04_validation_testing`
   - Live execution? -> `05_live_execution`
   - Risk/Safety? -> `06_safety_monitoring`
   - User ops/Content? -> `07_user_operations`

2. **Select Subdirectory**: Choose the appropriate subdirectory within the layer.
   - Example: A new scraper goes in `02_data_acquisition/web_scrapers/`.
   - Example: A new trading bot goes in `05_live_execution/trade_execution/` or `solana_trading/`.

3. **Create the File**:
   - Naming convention: `[purpose]_agent.py`
   - Example: `mytask_agent.py`

4. **Implement Base Structure**:
   Use the `ModelFactory` for AI model access.

   ```python
   from _engine._llm_providers.model_factory import ModelFactory
   from _engine.01_foundation.config import *
   # ... other imports

   class MyTaskAgent:
       def __init__(self):
           self.model = ModelFactory.create_model('anthropic')

       def run(self):
           print("Agent running...")
           # Logic here
   
   if __name__ == "__main__":
       agent = MyTaskAgent()
       agent.run()
   ```

5. **Register Agent** (Optional):
   - If the agent should run in the main loop, add it to `ACTIVE_AGENTS` in `_engine/main.py`.
