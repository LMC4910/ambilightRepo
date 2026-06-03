# Comprehensive Effect Mode Testing Script

$TOKEN = Get-Content auth_token
$BASE_URL = "http://localhost:7826"
$HEADERS = @{
    "Authorization" = "Bearer $TOKEN"
    "Content-Type" = "application/json"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "COMPREHENSIVE EFFECT MODE TEST SUITE" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$passCount = 0
$failCount = 0

# Test 1: Screen Sync Mode
Write-Host "[TEST 1] Screen Sync Mode" -ForegroundColor Yellow
try {
    $body = @{mode = "screen_sync"; params = @{}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Mode switched to screen_sync" -ForegroundColor Green
    $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
    Write-Host "  FPS: $($metrics.fps), Latency: $($metrics.latency_ms)ms" -ForegroundColor Gray
    $passCount++
    Start-Sleep -Milliseconds 500
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 2: Static Color Mode - Red
Write-Host "`n[TEST 2] Static Color Mode - Red (255,0,0)" -ForegroundColor Yellow
try {
    $body = @{mode = "static"; params = @{r = 255; g = 0; b = 0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Red static mode set" -ForegroundColor Green
    $passCount++
    Start-Sleep -Milliseconds 300
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 3: Static Color Mode - Green
Write-Host "`n[TEST 3] Static Color Mode - Green (0,255,0)" -ForegroundColor Yellow
try {
    $body = @{mode = "static"; params = @{r = 0; g = 255; b = 0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Green static mode set" -ForegroundColor Green
    $passCount++
    Start-Sleep -Milliseconds 300
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 4: Static Color Mode - Blue
Write-Host "`n[TEST 4] Static Color Mode - Blue (0,0,255)" -ForegroundColor Yellow
try {
    $body = @{mode = "static"; params = @{r = 0; g = 0; b = 255}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Blue static mode set" -ForegroundColor Green
    $passCount++
    Start-Sleep -Milliseconds 300
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 5: Static Color Mode - White
Write-Host "`n[TEST 5] Static Color Mode - White (255,255,255)" -ForegroundColor Yellow
try {
    $body = @{mode = "static"; params = @{r = 255; g = 255; b = 255}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] White static mode set" -ForegroundColor Green
    $passCount++
    Start-Sleep -Milliseconds 300
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 6: Breathing Effect - Speed 0.5
Write-Host "`n[TEST 6] Breathing Effect - Speed 0.5" -ForegroundColor Yellow
try {
    $body = @{mode = "breathing"; params = @{r = 255; g = 0; b = 0; speed = 0.5}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Breathing mode set (slow, speed 0.5)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 7: Breathing Effect - Speed 1.0
Write-Host "`n[TEST 7] Breathing Effect - Speed 1.0" -ForegroundColor Yellow
try {
    $body = @{mode = "breathing"; params = @{r = 0; g = 255; b = 0; speed = 1.0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Breathing mode set (normal, speed 1.0)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 8: Breathing Effect - Speed 2.0
Write-Host "`n[TEST 8] Breathing Effect - Speed 2.0" -ForegroundColor Yellow
try {
    $body = @{mode = "breathing"; params = @{r = 0; g = 0; b = 255; speed = 2.0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Breathing mode set (fast, speed 2.0)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 9: Rainbow Cycle - Speed 0.5
Write-Host "`n[TEST 9] Rainbow Cycle Effect - Speed 0.5" -ForegroundColor Yellow
try {
    $body = @{mode = "rainbow"; params = @{speed = 0.5}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Rainbow mode set (slow, speed 0.5)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 10: Rainbow Cycle - Speed 1.0
Write-Host "`n[TEST 10] Rainbow Cycle Effect - Speed 1.0" -ForegroundColor Yellow
try {
    $body = @{mode = "rainbow"; params = @{speed = 1.0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Rainbow mode set (normal, speed 1.0)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 11: Rainbow Cycle - Speed 2.0
Write-Host "`n[TEST 11] Rainbow Cycle Effect - Speed 2.0" -ForegroundColor Yellow
try {
    $body = @{mode = "rainbow"; params = @{speed = 2.0}} | ConvertTo-Json
    $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
    Write-Host "[PASS] Rainbow mode set (fast, speed 2.0)" -ForegroundColor Green
    for ($i = 0; $i -lt 4; $i++) {
        Start-Sleep -Milliseconds 500
        $metrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
        Write-Host "  Sample $($i+1): FPS=$($metrics.fps), Latency=$($metrics.latency_ms)ms" -ForegroundColor Gray
    }
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Test 12: Mode Transitions
Write-Host "`n[TEST 12] Mode Transitions - Rapid switching" -ForegroundColor Yellow
try {
    $modes = @("screen_sync", "static", "breathing", "rainbow", "static", "screen_sync")
    foreach ($mode in $modes) {
        if ($mode -eq "screen_sync") {
            $body = @{mode = "screen_sync"; params = @{}} | ConvertTo-Json
        } elseif ($mode -eq "static") {
            $body = @{mode = "static"; params = @{r = 255; g = 128; b = 0}} | ConvertTo-Json
        } elseif ($mode -eq "breathing") {
            $body = @{mode = "breathing"; params = @{r = 255; g = 0; b = 0; speed = 1.0}} | ConvertTo-Json
        } else {
            $body = @{mode = "rainbow"; params = @{speed = 1.0}} | ConvertTo-Json
        }
        $response = Invoke-RestMethod -Uri "$BASE_URL/api/mode" -Method PUT -Headers $HEADERS -Body $body
        Write-Host "  [OK] Switched to $mode" -ForegroundColor Green
        Start-Sleep -Milliseconds 200
    }
    Write-Host "[PASS] All transitions completed successfully" -ForegroundColor Green
    $passCount++
} catch {
    Write-Host "[FAIL] Error: $($_.Exception.Message)" -ForegroundColor Red
    $failCount++
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`nPassed: $passCount" -ForegroundColor Green
Write-Host "Failed: $failCount" -ForegroundColor $(if ($failCount -eq 0) { "Green" } else { "Red" })
Write-Host "Total: $($passCount + $failCount)" -ForegroundColor Cyan

# Display final metrics
Write-Host "`n[FINAL METRICS]" -ForegroundColor Yellow
try {
    $finalMetrics = Invoke-RestMethod -Uri "$BASE_URL/api/metrics" -Method GET -Headers $HEADERS
    Write-Host "FPS: $($finalMetrics.fps)" -ForegroundColor Gray
    Write-Host "Latency (ms): $($finalMetrics.latency_ms)" -ForegroundColor Gray
    Write-Host "Status: RUNNING" -ForegroundColor Green
} catch {
    Write-Host "Could not retrieve final metrics" -ForegroundColor Red
}

Write-Host "`n========================================`n" -ForegroundColor Cyan
