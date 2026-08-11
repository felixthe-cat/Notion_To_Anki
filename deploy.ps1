# deploy.ps1 — Copy the dev add-on into Anki's add-ons folder and restart Anki.
#
# Usage:
#   .\deploy.ps1           # copy files only (Anki must be restarted manually)
#   .\deploy.ps1 -Restart  # also kill and relaunch Anki automatically

param(
    [switch]$Restart
)

$src  = "$PSScriptRoot\notion_to_anki"
$dest = "$env:APPDATA\Anki2\addons21\notion_to_anki"

if (-not (Test-Path $dest)) {
    Write-Error "Destination not found: $dest"
    exit 1
}

# ---- Copy source files, skipping __pycache__ and .pyc ----
Write-Host "Deploying $src -> $dest" -ForegroundColor Cyan

# user_files/ and meta.json hold live state (the synced-card index, the saved
# token). Copying them over the installed add-on would clobber real sync history
# with whatever stale copy happens to sit in the repo.
Get-ChildItem -Path $src -Recurse -File |
    Where-Object {
        $_.FullName -notmatch '__pycache__' -and
        $_.FullName -notmatch '\\user_files\\' -and
        $_.Name -ne 'meta.json' -and
        $_.Extension -notin @('.pyc')
    } |
    ForEach-Object {
        $rel  = $_.FullName.Substring($src.Length)
        $target = Join-Path $dest $rel
        $targetDir = Split-Path $target -Parent

        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }

        Copy-Item -Path $_.FullName -Destination $target -Force
        Write-Host "  copied $rel"
    }

# ---- Remove stale bytecode in destination ----
Get-ChildItem -Path $dest -Recurse -Filter "*.pyc" | Remove-Item -Force
$pycacheDirs = Get-ChildItem -Path $dest -Recurse -Directory -Filter "__pycache__"
foreach ($d in $pycacheDirs) {
    if ((Get-ChildItem $d.FullName).Count -eq 0) {
        Remove-Item $d.FullName -Force
    }
}
Write-Host "Cleared .pyc cache" -ForegroundColor DarkGray

# ---- Optionally restart Anki ----
if ($Restart) {
    # The launcher hands off to "pythonw.exe -c import aqt; aqt.run()", so the
    # real Anki is NOT a process named "anki" — matching only that name killed
    # the launcher stub and left the running app on the old code. Match on the
    # AnkiProgramFiles venv path, which is specific enough not to hit anything else.
    $ankiIds = Get-CimInstance Win32_Process -Filter "Name='anki.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*AnkiProgramFiles*' -or $_.Name -eq 'anki.exe' } |
        Select-Object -ExpandProperty ProcessId

    if ($ankiIds) {
        Write-Host "Stopping Anki (PIDs: $($ankiIds -join ', '))..." -ForegroundColor Yellow
        foreach ($pid_ in $ankiIds) {
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
    }

    # Common Anki install locations
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Anki\anki.exe",
        "C:\Program Files\Anki\anki.exe",
        "C:\Program Files (x86)\Anki\anki.exe"
    )
    $ankiExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($ankiExe) {
        Write-Host "Launching $ankiExe" -ForegroundColor Green
        Start-Process $ankiExe
    } else {
        Write-Host "Anki executable not found in common locations - please launch Anki manually." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Deploy complete. Restart Anki to load the updated add-on." -ForegroundColor Green
