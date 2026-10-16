# Starts the API and the UI dev server in two background jobs and runs the browser acceptance script.
#   powershell -ExecutionPolicy Bypass -File scripts\run-windows.ps1 [-Verify] [-Push]
param([switch]$Verify, [switch]$Push, [int]$StartS = 600)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "$root\_logs" | Out-Null

Get-Process -Name python, node -ErrorAction SilentlyContinue | Where-Object { $_.Path -and ($_.CommandLine -match 'uvicorn|vite') } | Stop-Process -Force -ErrorAction SilentlyContinue

$env:TROSSOPS_START_S = "$StartS"
$api = Start-Process -FilePath python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory "$root\backend" -RedirectStandardOutput "$root\_logs\api.txt" -RedirectStandardError "$root\_logs\api-err.txt" -PassThru -WindowStyle Hidden
$ui = Start-Process -FilePath cmd.exe -ArgumentList '/c','npm run dev' -WorkingDirectory "$root\frontend" -RedirectStandardOutput "$root\_logs\ui.txt" -RedirectStandardError "$root\_logs\ui-err.txt" -PassThru -WindowStyle Hidden
"api pid $($api.Id) ui pid $($ui.Id) $(Get-Date -Format s)" | Set-Content "$root\_logs\run.txt"
Start-Sleep -Seconds 8
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health).Content | Add-Content "$root\_logs\run.txt" } catch { "health failed: $_" | Add-Content "$root\_logs\run.txt" }
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/).StatusCode | Add-Content "$root\_logs\run.txt" } catch { "ui failed: $_" | Add-Content "$root\_logs\run.txt" }

if ($Verify) {
  Push-Location frontend
  node scripts\verify-browser.mjs "$root\_logs\verify" 2>&1 | Tee-Object -FilePath "$root\_logs\verify.txt" | Out-Null
  Pop-Location
}
if ($Push) {
  git push -u origin main 2>&1 | Tee-Object -FilePath "$root\_logs\push.txt" | Out-Null
}
"DONE $(Get-Date -Format s)" | Add-Content "$root\_logs\run.txt"
