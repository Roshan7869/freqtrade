# rule.md

Rule description here...

## Guidelines

- Guideline 1
- Guideline 2
🏗️ Core Project Structure
Your project follows a Event-Driven Microservices architecture.

1. user_data/ (The Strategy Lab)
What it is: Where your trading logic lives.
Key Content: strategies/ contains your Freqtrade strategy files (e.g.,
AroonMomentumStrategy.py
).
Workflow: Strategies run here (via Freqtrade), analyze the market, and publish Signals to the system.
2. infrastructure/ (The Backbone)
What it is: Docker configuration for the system's plumbing.
Key Services:
Kafka: The central nervous system. All signals flow through here.
Zookeeper: Manages Kafka.
Redis: Fast caching for state.
Freqtrade: Runs the strategies inside containers.
3. decision_layer/ (The Brain)
What it is: The core execution logic.
Key File:
src/decision_engine.py
Workflow:
Listens: Consumes "Signal" events from Kafka (signal.strategy, signal.whale).
Buffers: Waits for confirmation (e.g., "Need 2 signals for SOL").
Decides: Aggregates votes (Buy vs Sell).
Acts: Publishes a trade.order event to execute the trade.
🔄 Core Execution Workflow
How a trade happens, step-by-step:

Signal Generation:

AroonMomentumStrategy
 (in user_data) detects a Buy setup.
Sends
Signal(symbol="SOL/USDT", action="BUY")
 to Kafka topic signal.strategy.
Signal Processing:

DecisionEngine
 (in decision_layer) picks up the message.
It sees the vote but waits (buffer logic) or checks for conflict.
Execution:

If conditions are met (e.g., >50% buy votes), the Engine sends a
TradeOrder
.
The Execution Layer (another service) picks this up and places the actual order on Binance.
🛠️ Summary of "These Folders"
.kilocode: Agent Tools Config.
user_data: Trading Strategies.
decision_layer: Aggregation Logic.
infrastructure: System Servers (Kafka/Docker).
