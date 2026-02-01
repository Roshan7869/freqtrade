# 300-Day Backtest Runner
# Run this in PowerShell to download data and backtest XRP, DOGE, SOL

# Calculate dates (300 days back)
$endDate = Get-Date
$startDate = $endDate.AddDays(-300)
$timerange = "{0}-{1}" -f $startDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "300-DAY BACKTEST: XRP, DOGE, SOL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Timerange: $timerange (300 days)" -ForegroundColor Yellow
Write-Host ""

# Pairs and timeframes
$pairs = @("XRP/USDT:USDT", "DOGE/USDT:USDT", "SOL/USDT:USDT")
$timeframes = @("5m", "15m", "1h", "4h", "1d")

# Step 1: Download Data
Write-Host "============================================================" -ForegroundColor Green
Write-Host "STEP 1: DOWNLOADING DATA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$downloadCount = 0
$totalDownloads = $pairs.Count * $timeframes.Count

foreach ($pair in $pairs) {
    foreach ($tf in $timeframes) {
        $downloadCount++
        Write-Host "[$downloadCount/$totalDownloads] Downloading $pair $tf..." -ForegroundColor Yellow
        
        docker run --rm `
            -v "${PWD}/user_data:/freqtrade/user_data" `
            freqtradeorg/freqtrade:stable `
            download-data `
            --config /freqtrade/user_data/config.json `
            --pairs $pair `
            --timeframes $tf `
            --timerange $timerange `
            --exchange binance `
            --trading-mode futures
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Success" -ForegroundColor Green
        }
        else {
            Write-Host "  [ERROR] Failed" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "[COMPLETE] Data download finished!" -ForegroundColor Green
Write-Host ""

# Step 2: Get all strategies
Write-Host "============================================================" -ForegroundColor Green
Write-Host "STEP 2: PREPARING BACKTESTS" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$strategies = Get-ChildItem -Path "user_data/strategies" -Filter "*.py" | 
Where-Object { $_.BaseName -notin @("__init__", "path_setup") -and !$_.BaseName.StartsWith(".") } |
Select-Object -ExpandProperty BaseName

Write-Host "Found $($strategies.Count) strategies" -ForegroundColor Yellow
Write-Host "Testing on $($pairs.Count) pairs" -ForegroundColor Yellow
Write-Host "Total backtests: $($strategies.Count * $pairs.Count)" -ForegroundColor Yellow
Write-Host ""

# Step 3: Run Backtests
Write-Host "============================================================" -ForegroundColor Green
Write-Host "STEP 3: RUNNING BACKTESTS" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$results = @{}
$testCount = 0
$totalTests = $strategies.Count * $pairs.Count

foreach ($strategy in $strategies) {
    $results[$strategy] = @{}
    
    foreach ($pair in $pairs) {
        $testCount++
        Write-Host "[$testCount/$totalTests] Testing $strategy on $pair..." -ForegroundColor Yellow
        
        docker run --rm `
            -v "${PWD}/user_data:/freqtrade/user_data" `
            freqtradeorg/freqtrade:stable `
            backtesting `
            --config /freqtrade/user_data/config.json `
            --strategy $strategy `
            --timerange $timerange `
            --pairs $pair `
            --timeframe 1h `
            --export trades
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Success" -ForegroundColor Green
            $results[$strategy][$pair] = "SUCCESS"
        }
        else {
            Write-Host "  [ERROR] Failed" -ForegroundColor Red
            $results[$strategy][$pair] = "FAILED"
        }
    }
}

# Step 4: Analyze Results
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "STEP 4: RESULTS SUMMARY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$strategyScores = @{}
foreach ($strategy in $results.Keys) {
    $successCount = ($results[$strategy].Values | Where-Object { $_ -eq "SUCCESS" }).Count
    $strategyScores[$strategy] = $successCount
}

$topStrategies = $strategyScores.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10

Write-Host ""
Write-Host "TOP 10 STRATEGIES:" -ForegroundColor Cyan
Write-Host ("{0,-6} {1,-40} {2,-15}" -f "Rank", "Strategy", "Success Rate") -ForegroundColor White
Write-Host ("-" * 60) -ForegroundColor Gray

$rank = 1
foreach ($item in $topStrategies) {
    $successRate = "$($item.Value)/$($pairs.Count)"
    Write-Host ("{0,-6} {1,-40} {2,-15}" -f $rank, $item.Key, $successRate)
    $rank++
}

# Save results to JSON
$resultsData = @{
    timerange         = $timerange
    pairs             = $pairs
    strategies_tested = $strategies.Count
    results           = $results
    top_strategies    = $topStrategies | Select-Object -ExpandProperty Key
}

$resultsFile = "user_data/backtest_300days_results.json"
$resultsData | ConvertTo-Json -Depth 10 | Out-File -FilePath $resultsFile -Encoding UTF8

Write-Host ""
Write-Host "[SAVED] Results saved to: $resultsFile" -ForegroundColor Green
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[COMPLETE] WORKFLOW FINISHED!" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
