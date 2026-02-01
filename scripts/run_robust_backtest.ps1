# Robust Backtest Workflow
# Ensures all data requirements are met before running strategies

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Green
Write-Host "   QUANT TACTICS ROBUST BACKTEST SYSTEM   " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Analyze Requirements
Write-Host "`n[1/3] Analyzing Strategy Requirements..." -ForegroundColor Cyan
python scripts/analyze_strategy_requirements.py
if ($LASTEXITCODE -ne 0) { Write-Error "Analysis failed"; exit }

# 2. Download Data
Write-Host "`n[2/3] Downloading Required Data (Smart Download)..." -ForegroundColor Cyan
python scripts/download_required_data.py
if ($LASTEXITCODE -ne 0) { Write-Error "Data download failed"; exit }

# 3. Run Backtests
Write-Host "`n[3/3] Executing Robust Backtest Runner..." -ForegroundColor Cyan
python scripts/robust_backtest.py

Write-Host "`nWork Complete!" -ForegroundColor Green
