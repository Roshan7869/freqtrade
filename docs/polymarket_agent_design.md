# Polymarket AI Agent Design Document

## Overview

A sophisticated AI-powered prediction market agent that monitors Polymarket trades in real-time, analyzes market opportunities using multiple AI models, and provides consensus-based trading recommendations.

## Architecture

### Core Components

#### 1. **Real-Time Data Collection**

- **WebSocket Connection**: Live connection to Polymarket's trade feed (`wss://ws-live-data.polymarket.com`)
- **Historical Data Fetching**: REST API integration for backfilling recent trades
- **Trade Filtering**:
  - Minimum trade size: $500 USD
  - Excludes near-resolution prices (within 2¢ of $0 or $1)
  - Category filters: Ignores crypto/sports markets (configurable)

#### 2. **AI Analysis Engine**

- **Swarm Mode** (Default): Queries 6+ AI models in parallel
  - Claude 4.5 Sonnet
  - GPT-5
  - Gemini 2.5
  - Grok-4
  - DeepSeek
  - DeepSeek-R1 (local)
- **Single Model Mode**: Fallback to individual AI (e.g., Grok-2-fast-reasoning)
- **Consensus Algorithm**: Identifies markets with strongest AI agreement

#### 3. **Data Storage**

- **markets.csv**: All tracked markets with metadata
  - Columns: timestamp, market_id, event_slug, title, outcome, price, size_usd, first_seen, last_analyzed, last_trade_timestamp
- **predictions.csv**: Historical AI predictions
  - Columns: analysis_timestamp, analysis_run_id, market_title, individual model predictions, consensus_prediction, num_models_responded, market_link
- **consensus_picks.csv**: Top consensus picks from each analysis run

## Key Features

### 1. **Smart Market Discovery**

- Monitors all Polymarket trades in real-time
- Filters out noise (small trades, resolved markets, unwanted categories)
- Tracks market freshness (last trade timestamp)

### 2. **Multi-Model AI Analysis**

- Analyzes markets every 5 minutes or when 3+ new markets appear
- Each AI model provides: YES/NO/NO_TRADE decision + reasoning
- Consensus engine identifies strongest agreement across models
- Re-analysis after 8 hours to catch market changes

### 3. **Configurable Intelligence**

```python
# Price Information Toggle
SEND_PRICE_INFO_TO_AI = False  # Blind analysis (no price bias)
# or
SEND_PRICE_INFO_TO_AI = True   # Include current odds

# Analysis Triggers
ANALYSIS_CHECK_INTERVAL_SECONDS = 300  # Check every 5 min
NEW_MARKETS_FOR_ANALYSIS = 3           # Trigger on 3 new markets
MARKETS_TO_ANALYZE = 3                 # Analyze last 3 markets
```

### 4. **Consensus Ranking**

- Final AI pass to identify top 5 markets with strongest consensus
- Ranks by agreement strength (e.g., "5 out of 6 models agreed")
- Provides clickable Polymarket links for immediate review

## Workflow

### Initialization

1. Load existing markets and predictions from CSV
2. Initialize AI models (swarm or single)
3. Fetch last 24 hours of historical trades
4. Connect to WebSocket for live trades

### Real-Time Operation

1. **Trade Reception** (WebSocket)
   - Filter by size, price, category
   - Add new markets or update existing
   - Save to markets.csv

2. **Analysis Trigger** (Every 5 min or 3+ new markets)
   - Select recent unanalyzed markets
   - Query AI swarm with market details
   - Parse individual model predictions
   - Calculate consensus
   - Identify top consensus picks
   - Save to predictions.csv and consensus_picks.csv

3. **Status Monitoring**
   - Display recent markets
   - Show trade statistics
   - Track AI response rates

## Integration Points

### For Freqtrade Integration

To integrate this Polymarket agent with your Freqtrade system:

1. **Data Bridge**
   - Read `consensus_picks.csv` for high-confidence markets
   - Map Polymarket events to trading signals
   - Example: "Bitcoin to hit $100k by March" → BTC/USDT long position

2. **Signal Translation**

   ```python
   # Polymarket YES → Freqtrade LONG
   # Polymarket NO → Freqtrade SHORT
   # Polymarket NO_TRADE → Skip
   ```

3. **Risk Management**
   - Use consensus strength as position sizing factor
   - Higher consensus (5/6 models) → Larger position
   - Lower consensus (3/6 models) → Smaller position

4. **Execution Strategy**
   - Create new Freqtrade strategy: `PolymarketSignalStrategy.py`
   - Poll `consensus_picks.csv` every 5 minutes
   - Execute trades based on AI consensus
   - Set stop-loss based on market resolution date

## Configuration Recommendations

### For Trading (High Precision)

```python
MIN_TRADE_SIZE_USD = 1000  # Only big money trades
MARKETS_TO_ANALYZE = 5     # More context
TOP_MARKETS_COUNT = 3      # Only best picks
SEND_PRICE_INFO_TO_AI = False  # Avoid price anchoring
```

### For Research (Broad Coverage)

```python
MIN_TRADE_SIZE_USD = 500
MARKETS_TO_ANALYZE = 10
TOP_MARKETS_COUNT = 10
SEND_PRICE_INFO_TO_AI = True  # Include all data
```

## Deployment

### Requirements

- Python 3.10+
- API Keys: Anthropic, OpenAI, Google, xAI, DeepSeek, Groq
- Dependencies: `websocket-client`, `pandas`, `requests`, `termcolor`

### Running the Agent

```bash
cd "Algo @ 2/MoondevRED"
python _engine/07_user_operations/user_engagement/polymarket_agent.py
```

### Output Files

- `src/data/polymarket/markets.csv` - All markets
- `src/data/polymarket/predictions.csv` - All predictions
- `src/data/polymarket/consensus_picks.csv` - Top picks only

## Advanced Features

### 1. **Category Filtering**

Customize ignored markets:

```python
IGNORE_CRYPTO_KEYWORDS = ['bitcoin', 'eth', 'solana']
IGNORE_SPORTS_KEYWORDS = ['nba', 'nfl', 'ufc']
```

### 2. **Re-Analysis Logic**

Markets are re-analyzed after 8 hours to catch:

- Odds changes
- New information
- Market momentum shifts

### 3. **Blind vs. Informed Analysis**

- **Blind** (`SEND_PRICE_INFO_TO_AI = False`): AI sees only question, no odds
  - Reduces bias, finds value bets
- **Informed** (`SEND_PRICE_INFO_TO_AI = True`): AI sees current odds
  - Better for arbitrage, momentum plays

## Future Enhancements

1. **Auto-Trading Module**
   - Direct Polymarket API integration
   - Automated bet placement based on consensus
   - Position sizing based on Kelly Criterion

2. **Backtesting Engine**
   - Replay historical predictions
   - Calculate ROI if bets were placed
   - Optimize consensus thresholds

3. **Telegram/Discord Alerts**
   - Real-time notifications for high-consensus picks
   - Daily summary reports
   - Performance tracking

4. **Freqtrade Strategy Generator**
   - Auto-generate strategies from Polymarket signals
   - Map prediction markets to crypto pairs
   - Dynamic position sizing based on consensus strength

## Conclusion

This Polymarket AI Agent provides a robust foundation for prediction market analysis. The multi-model consensus approach reduces individual AI bias, while the real-time WebSocket feed ensures you never miss emerging opportunities.

**Key Advantage**: By using 6+ AI models, you get a "wisdom of the crowd" effect that's more reliable than any single model's prediction.

**Next Steps for Integration**:

1. Run the agent to build a prediction history
2. Analyze which consensus levels are most profitable
3. Create Freqtrade strategy that acts on high-consensus picks
4. Backtest the combined system before live deployment
