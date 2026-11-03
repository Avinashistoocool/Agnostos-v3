param([string]$Python = "python")

# Native build tools use stderr for progress; their exit codes are checked below.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$env:BROWSERSLIST_IGNORE_OLD_DATA = "1"
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "Frontend build dependencies failed to install" }
npm run build:css
if ($LASTEXITCODE -ne 0) { throw "Offline stylesheet failed to build" }

& $Python -m pip install -r desktop-requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Desktop dependencies failed to install" }

$assets = @(
    "web\app.html", "web\app.js", "web\researchers.js",
    "web\index.html", "web\site.css", "web\softly.css", "web\softly.js",
    "web\favicon.png", "web\apple-touch-icon.png", "web\og.png",
    "web\robots.txt", "web\sitemap.xml", "web\site.webmanifest"
)
$fonts = @(
    "outfit-latin-300-normal.woff2", "outfit-latin-400-normal.woff2",
    "outfit-latin-500-normal.woff2", "outfit-latin-600-normal.woff2",
    "reenie-beanie-latin-400-normal.woff2",
    "outfit-OFL.txt", "reenie-beanie-OFL.txt"
)
$data = @("--add-data", "sources.yaml;.", "--add-data", "server\migrations\env.py;server\migrations")
foreach ($migration in Get-ChildItem "server\migrations\versions" -Filter "*.py" -File) {
    $data += @("--add-data", "$($migration.FullName);server\migrations\versions")
}
foreach ($asset in $assets) { $data += @("--add-data", "$asset;web") }
foreach ($font in $fonts) { $data += @("--add-data", "web\fonts\$font;web\fonts") }

& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name Agnostos --distpath dist --workpath build\desktop $data `
    --collect-submodules outreach --collect-submodules server `
    --collect-submodules sqlalchemy.dialects --collect-submodules alembic desktop.py
if ($LASTEXITCODE -ne 0) { throw "Desktop build failed" }

$sensitive = Get-ChildItem dist\Agnostos -Recurse -File |
    Where-Object { $_.Name -eq ".env" -or $_.Name -like "*.env" -or
                   $_.Name -eq ".app_secret" -or $_.Name -like "*.db" }
if ($sensitive) { throw "Sensitive files found in desktop distribution: $($sensitive.FullName -join ', ')" }
Write-Host "Built dist\Agnostos\Agnostos.exe (distribute the entire Agnostos folder)."
