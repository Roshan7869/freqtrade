# Freqtrade Control Panel - PowerShell Interface
# Use this script to configure and launch backtests or live trading

$ErrorActionPreference = "Stop"

Clear-Host
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   QUANT TACTICS TRADING CONTROL PANEL    " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Select Mode
Write-Host "`n[1] Select Operation Mode:" -ForegroundColor Yellow
Write-Host "1. Backtest (Simulation)"
Write-Host "2. Trade (Live or Dry-Run)"
$mode = Read-Host "Choice (1 or 2)"

# 2. Financial Configuration
Write-Host "`n[2] Global Strategy Configuration:" -ForegroundColor Yellow
$leverage = Read-Host "Enter Leverage (e.g., 6 or 12)"
$principal = Read-Host "Enter Principal Amount (USDT)"

# 3. Strategy Selection
Write-Host "`n[3] Strategy Selection:" -ForegroundColor Yellow
$strategy = Read-Host "Enter Strategy Name (e.g., RSISMAMomentumStrategy)"

# Update Configuration Files
Function Update-Config {
    param($FilePath, $Lev, $Wallet)
    if (Test-Path $FilePath) {
        $config = Get-Content $FilePath | ConvertFrom-Json
        $config.leverage = [int]$Lev
        $config.dry_run_wallet = [int]$Wallet
        $config | ConvertTo-Json -Depth 10 | Set-Content $FilePath
        Write-Host "Updated config: $FilePath" -ForegroundColor Green
    }
}

Update-Config -FilePath "user_data/config_backtest.json" -Lev $leverage -Wallet $principal
Update-Config -FilePath "user_data/config.json" -Lev $leverage -Wallet $principal

# 4. Mode Specific Logic
if ($mode -eq "1") {
    # Backtest Logic
    Write-Host "`n[4] Backtest Parameters:" -ForegroundColor Yellow
    $timerange = Read-Host "Enter Timerange (e.g. 20250101- or specific days like 30)"
    $tokens = Read-Host "Enter Pairs (e.g. SOL/USDT:USDT)"

    Write-Host "`nLaunching Backtest..." -ForegroundColor Cyan
    
    # Check if timerange is just a number (days)
    if ($timerange -match "^\d+$") {
        # It's a number of days. For simplicity, we trigger the chunked backtest or a simple backtest.
        # Logic: Calculate start date based on today
        $startDate = (Get-Date).AddDays( - [int]$timerange).ToString("yyyyMMdd")
        $finalTimerange = "$startDate-"
    }
    else {
        $finalTimerange = $timerange
    }

    python scripts/robust_backtest.py --strategy $strategy --timerange $finalTimerange --pairs $tokens

}
elseif ($mode -eq "2") {
    # Trade Logic
    Write-Host "`n[4] Trade Initialization..." -ForegroundColor Yellow
    Write-Host "Note: This will use the settings in user_data/config.json"
    
    # Launch Docker Trade
    docker compose -f infrastructure/docker-compose.yml up -d
    Write-Host "Trading bot started in background." -ForegroundColor Green
    Write-Host "Use 'docker logs -f freqtrade' to view activity."
}
else {
    Write-Error "Invalid selection."
}

Write-Host "`nTask Complete!" -ForegroundColor Cyan
