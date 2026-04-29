$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$version = py -c "from chickenwing import __version__; print(__version__)"
$artifactRoot = Join-Path $repoRoot "release"
$artifactName = "chickenwing-windows-x64-v$version"
$artifactDir = Join-Path $artifactRoot $artifactName
$zipPath = Join-Path $artifactRoot "$artifactName.zip"

Write-Host "Installing build dependencies..."
py -m pip install .[build]

Write-Host "Cleaning old build output..."
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path $artifactDir) { Remove-Item $artifactDir -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "Building Chickenwing executable..."
py -m PyInstaller chickenwing.spec --noconfirm --clean

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
Copy-Item dist\chickenwing $artifactDir -Recurse

Write-Host "Creating release zip..."
Compress-Archive -Path $artifactDir -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Build complete:"
Write-Host "  Folder: $artifactDir"
Write-Host "  Zip:    $zipPath"
