# Test Configuration Hot-Reload

# Part 1: Get baseline config and auth token
Write-Host "=== PART 1: BASELINE CONFIGURATION ===" -ForegroundColor Cyan

# Try to get auth token from file
$tokenFile = "auth_token"
if (Test-Path $tokenFile) {
    $token = Get-Content $tokenFile -Raw
    Write-Host "Token loaded from file: $($token.Substring(0, 20))..."
} else {
    Write-Host "No auth token file found"
    $token = ""
}

# Get baseline config
Write-Host "`nGetting baseline config..."
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Get -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    $baselineConfig = $response.Content | ConvertFrom-Json
    Write-Host "Baseline Config loaded successfully" -ForegroundColor Green

    # Extract key baseline values
    $colorMode = $baselineConfig.color.mode
    $fps = $baselineConfig.capture.fps_target
    $smoothing = $baselineConfig.smoothing.base_alpha

    Write-Host "`nBaseline Values:"
    Write-Host "  Color Mode: $colorMode"
    Write-Host "  FPS Target: $fps"
    Write-Host "  Smoothing (base_alpha): $smoothing"
} catch {
    Write-Host "Error getting baseline config: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Part 2: Update color mode
Write-Host "`n=== PART 2: UPDATE COLOR MODE ===" -ForegroundColor Cyan
Write-Host "Updating color mode to 'kmeans'..."

try {
    $updatePayload = @{
        color = @{
            mode = "kmeans"
        }
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Put -Body $updatePayload -ContentType "application/json" -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    Write-Host "Response: $($response.Content)" -ForegroundColor Green
    Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Wait a bit for the update
Start-Sleep -Seconds 1

# Part 3: Verify color mode changed
Write-Host "`n=== PART 3: VERIFY COLOR MODE CHANGED ===" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Get -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    $updatedConfig = $response.Content | ConvertFrom-Json
    $newColorMode = $updatedConfig.color.mode
    Write-Host "New Color Mode: $newColorMode"

    if ($newColorMode -eq "kmeans") {
        Write-Host "✓ Color mode update SUCCESSFUL" -ForegroundColor Green
    } else {
        Write-Host "✗ Color mode update FAILED - expected 'kmeans', got '$newColorMode'" -ForegroundColor Red
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Update FPS
Write-Host "`nUpdating FPS target to 60..."
try {
    $updatePayload = @{
        capture = @{
            fps_target = 60
        }
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Put -Body $updatePayload -ContentType "application/json" -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ FPS update response: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}

Start-Sleep -Seconds 1

# Part 4: Test multiple config changes without restart
Write-Host "`n=== PART 4: MULTIPLE CONFIG CHANGES ===" -ForegroundColor Cyan

# Update 1: Smoothing
Write-Host "Update 1: Setting smoothing base_alpha to 0.25..."
try {
    $updatePayload = @{
        smoothing = @{
            base_alpha = 0.25
        }
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Put -Body $updatePayload -ContentType "application/json" -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Update successful (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "✗ Update failed: $($_.Exception.Message)" -ForegroundColor Red
}

Start-Sleep -Seconds 1

# Update 2: Zones
Write-Host "Update 2: Setting zones (top: 10, bottom: 10)..."
try {
    $updatePayload = @{
        zones = @{
            top = 10
            bottom = 10
        }
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Put -Body $updatePayload -ContentType "application/json" -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Update successful (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "✗ Update failed: $($_.Exception.Message)" -ForegroundColor Red
}

Start-Sleep -Seconds 1

# Update 3: Logging
Write-Host "Update 3: Setting logging level to DEBUG..."
try {
    $updatePayload = @{
        logging = @{
            level = "DEBUG"
        }
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Put -Body $updatePayload -ContentType "application/json" -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Update successful (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "✗ Update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Part 5: Final verification
Write-Host "`n=== PART 5: FINAL VERIFICATION ===" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:7826/api/config" -Method Get -Headers @{"Authorization" = "Bearer $token"} -UseBasicParsing -ErrorAction Stop
    $finalConfig = $response.Content | ConvertFrom-Json

    Write-Host "Final Config Values:"
    Write-Host "  Color Mode: $($finalConfig.color.mode)"
    Write-Host "  FPS Target: $($finalConfig.capture.fps_target)"
    Write-Host "  Smoothing (base_alpha): $($finalConfig.smoothing.base_alpha)"
    Write-Host "  Zones (top): $($finalConfig.zones.top)"
    Write-Host "  Zones (bottom): $($finalConfig.zones.bottom)"
    Write-Host "  Logging Level: $($finalConfig.logging.level)"
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== TEST COMPLETE ===" -ForegroundColor Cyan
