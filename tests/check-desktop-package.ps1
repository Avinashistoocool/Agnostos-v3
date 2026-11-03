$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$package = Join-Path (Get-Location) "dist\Agnostos"
$exe = Join-Path $package "Agnostos.exe"

$required = @(
    "Agnostos.exe", "_internal\web\site.css", "_internal\web\softly.css",
    "_internal\web\index.html", "_internal\web\app.html",
    "_internal\web\app.js", "_internal\web\researchers.js",
    "_internal\web\fonts\outfit-latin-400-normal.woff2",
    "_internal\web\fonts\reenie-beanie-latin-400-normal.woff2",
    "_internal\web\fonts\outfit-OFL.txt",
    "_internal\web\fonts\reenie-beanie-OFL.txt",
    "_internal\sources.yaml",
    "_internal\server\migrations\env.py"
)
foreach ($file in $required) {
    if (-not (Test-Path (Join-Path $package $file) -PathType Leaf)) {
        throw "Missing desktop distribution asset: $file"
    }
}
foreach ($notice in "outfit-OFL.txt", "reenie-beanie-OFL.txt") {
    $text = Get-Content (Join-Path $package "_internal\web\fonts\$notice") -Raw
    if ($text -notmatch "Copyright" -or $text -notmatch "SIL OPEN FONT LICENSE") {
        throw "Font redistribution notice is missing attribution or license: $notice"
    }
}

function Assert-NoPrivateFiles {
    $privateFiles = Get-ChildItem $package -Recurse -File | Where-Object {
        $_.Name -eq ".env" -or $_.Name -like "*.env" -or
        $_.Name -eq ".app_secret" -or
        $_.Name -match "\.(db|sqlite|sqlite3)(-wal|-shm)?$"
    }
    if ($privateFiles) {
        throw "Private files found in desktop distribution: $($privateFiles.FullName -join ', ')"
    }
}

Assert-NoPrivateFiles
$data = Join-Path (Get-Location) "build\packaged-check-data"
$oldLocalAppData = $env:LOCALAPPDATA
$oldDatabaseUrl = $env:DATABASE_URL
$oldSending = $env:AGNOSTOS_LIVE_SEND_ENABLED
try {
    $env:LOCALAPPDATA = $data
    $env:DATABASE_URL = "postgresql://not-a-real-server/invalid"
    $env:AGNOSTOS_LIVE_SEND_ENABLED = "true"
    $process = Start-Process -FilePath $exe -ArgumentList "--health-check" -PassThru
    if (-not $process.WaitForExit(60000)) {
        Stop-Process -Id $process.Id
        throw "Packaged desktop health check timed out"
    }
    if ($process.ExitCode -ne 0) {
        $errorLog = Join-Path $data "Agnostos\startup-error.log"
        if (Test-Path $errorLog) { Get-Content $errorLog }
        throw "Packaged desktop health check failed with exit code $($process.ExitCode)"
    }
    foreach ($file in "agnostos.db", ".app_secret") {
        if (-not (Test-Path (Join-Path $data "Agnostos\$file") -PathType Leaf)) {
            throw "Desktop did not create per-user data: $file"
        }
    }
    Assert-NoPrivateFiles
    Write-Host "Packaged desktop health, assets, font licenses, and data isolation passed."
} finally {
    $env:LOCALAPPDATA = $oldLocalAppData
    $env:DATABASE_URL = $oldDatabaseUrl
    $env:AGNOSTOS_LIVE_SEND_ENABLED = $oldSending
    if (Test-Path $data) { Remove-Item $data -Recurse -Force }
}
