$ErrorActionPreference = "Continue"

Write-Host "Waiting for Docker to initialize..."
$dockerStarted = $false
for ($i = 0; $i -lt 15; $i++) {
    docker ps > $null 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker is UP!"
        $dockerStarted = $true
        break
    }
    Write-Host "Docker not ready, sleeping 5s..."
    Start-Sleep -Seconds 5
}

if (-not $dockerStarted) {
    Write-Error "Docker failed to start within 75 seconds. Please check Docker Desktop manually."
    exit 1
}

Write-Host "Downloading Data for SOL and DOGE (180 days)..."
docker compose -f infrastructure/docker-compose.download.yml run --rm freqtrade-download download-data --pairs SOL/USDT:USDT DOGE/USDT:USDT --timeframes 1h --days 180 --trading-mode futures --exchange binance

Write-Host "Running Backtest for AroonMomentumStrategy (12x Leverage)..."
# Using 180 days ago approx 20250726 to today 20260126
docker compose -f infrastructure/docker-compose.backtest.yml run --rm freqtrade-backtest backtesting --config /freqtrade/user_data/config_backtest.json --strategy AroonMomentumStrategy --pairs SOL/USDT:USDT DOGE/USDT:USDT --timerange 20250726-20260126 --timeframe 1h

Write-Host "Backtest execution finished."
