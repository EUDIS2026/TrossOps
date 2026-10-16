# One-shot setup on the owner's Windows machine. Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
# Restores git history from trossops.bundle (if .git is missing), installs dependencies, runs the checks,
# and writes every log to _logs\ so the result can be read without a terminal.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "$root\_logs" | Out-Null
$log = "$root\_logs\setup.txt"
"TrossOps setup $(Get-Date -Format s)" | Set-Content $log

function Step($name, $script) {
  "`n=== $name ===" | Add-Content $log
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try { & $script 2>&1 | Tee-Object -FilePath $log -Append | Out-Null; "exit=$LASTEXITCODE time=$($sw.Elapsed.TotalSeconds.ToString('0'))s" | Add-Content $log }
  catch { "ERROR: $_" | Add-Content $log }
}

Step 'versions' { git --version; node --version; npm --version; python --version }

if (-not (Test-Path "$root\.git")) {
  Step 'git restore history from bundle' {
    git init -b main
    git fetch "$root\trossops.bundle" main
    git reset --mixed FETCH_HEAD
    git remote add origin https://github.com/EUDIS2026/TrossOps.git
    git log --oneline | Select-Object -First 20
    git status --short | Select-Object -First 20
  }
}

Step 'backend dependencies' { python -m pip install -r backend\requirements.txt --disable-pip-version-check }
Step 'backend tests' { Push-Location backend; python -m pytest -q; Pop-Location }
Step 'frontend install' { Push-Location frontend; npm install --no-audit --no-fund; Pop-Location }
Step 'frontend typecheck' { Push-Location frontend; npm run typecheck; Pop-Location }
Step 'frontend unit tests' { Push-Location frontend; npm test; Pop-Location }
Step 'frontend build' { Push-Location frontend; npm run build; Pop-Location }
Step 'playwright browser' { Push-Location frontend; npx playwright install chromium; Pop-Location }
"`nDONE $(Get-Date -Format s)" | Add-Content $log
