$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$ffmpegVersion = "8.1.1"
$ffmpegArchiveName = "ffmpeg-8.1.1-essentials_build.zip"
$ffmpegReleaseApi = "https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/$ffmpegVersion"

$version = py -c "from chickenwing import __version__; print(__version__)"
$artifactRoot = Join-Path $repoRoot "release"
$artifactName = "chickenwing-windows-x64-v$version"
$artifactDir = Join-Path $artifactRoot $artifactName
$zipPath = Join-Path $artifactRoot "$artifactName.zip"
$vendorRoot = Join-Path $repoRoot ".tools\ffmpeg"
$ffmpegZip = Join-Path $vendorRoot $ffmpegArchiveName
$ffmpegExtract = Join-Path $vendorRoot "extract"

Write-Host "Installing build dependencies..."
py -m pip install .[build]

Write-Host "Cleaning old build output..."
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path $artifactDir) { Remove-Item $artifactDir -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "Fetching bundled ffmpeg..."
New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null
$release = Invoke-RestMethod -Uri $ffmpegReleaseApi -Headers @{ "User-Agent" = "chickenwing-build" }
$asset = $release.assets | Where-Object { $_.name -eq $ffmpegArchiveName } | Select-Object -First 1
if (-not $asset) {
    throw "Could not find ffmpeg asset '$ffmpegArchiveName' in release $ffmpegVersion."
}

Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ffmpegZip

$expectedSha = ($asset.digest -replace '^sha256:', '').Trim().ToUpper()
$actualSha = (Get-FileHash $ffmpegZip -Algorithm SHA256).Hash.ToUpper()
if ($expectedSha -ne $actualSha) {
    throw "Bundled ffmpeg SHA256 mismatch. Expected $expectedSha but got $actualSha."
}

if (Test-Path $ffmpegExtract) { Remove-Item $ffmpegExtract -Recurse -Force }
Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force

Write-Host "Building Chickenwing executable..."
py -m PyInstaller chickenwing.spec --noconfirm --clean

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
Copy-Item dist\chickenwing $artifactDir -Recurse

$ffmpegBuildDir = Get-ChildItem $ffmpegExtract -Directory | Select-Object -First 1
if (-not $ffmpegBuildDir) {
    throw "Bundled ffmpeg extraction did not produce a build directory."
}

$bundleTarget = Join-Path $artifactDir "ffmpeg\bin"
New-Item -ItemType Directory -Force -Path $bundleTarget | Out-Null
Copy-Item (Join-Path $ffmpegBuildDir.FullName "bin\ffmpeg.exe") $bundleTarget -Force
Copy-Item (Join-Path $ffmpegBuildDir.FullName "bin\ffprobe.exe") $bundleTarget -Force

$licenseSource = Join-Path $ffmpegBuildDir.FullName "LICENSE"
if (Test-Path $licenseSource) {
    New-Item -ItemType Directory -Force -Path (Join-Path $artifactDir "ffmpeg") | Out-Null
    Copy-Item $licenseSource (Join-Path $artifactDir "ffmpeg\LICENSE") -Force
}

Write-Host "Creating release zip..."
Compress-Archive -Path $artifactDir -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Build complete:"
Write-Host "  Folder: $artifactDir"
Write-Host "  Zip:    $zipPath"
