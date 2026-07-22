[CmdletBinding()]
param(
    [string]$PythonCommand = "py",
    [string]$Version = "1.2.1",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$SourceFile = Join-Path $Root "build_meccha_mod.py"
$SpecFile = Join-Path $Root "MecchaModBuilder.spec"
$ResourcesDir = Join-Path $Root "resources"
$ReadmeFile = Join-Path $Root "README.md"
$LicenseFile = Join-Path $Root "LICENSE"
$VersionFile = Join-Path $Root "version_info.txt"

$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$ReleaseRoot = Join-Path $Root "release"
$ReleaseName = "Meccha-Mod-Builder-v$Version"
$ReleaseDir = Join-Path $ReleaseRoot $ReleaseName
$ZipPath = Join-Path $ReleaseRoot "$ReleaseName.zip"
$ChecksumPath = "$ZipPath.sha256"

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Label`: $Path"
    }
}

function Assert-DirectoryExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Missing $Label`: $Path"
    }
}

Write-Host ""
Write-Host "=== Meccha Mod Builder v$Version Release Build ===" -ForegroundColor Cyan

Assert-FileExists -Path $SourceFile -Label "application source"
Assert-FileExists -Path $SpecFile -Label "PyInstaller spec"
Assert-FileExists -Path $ReadmeFile -Label "README"
Assert-FileExists -Path $LicenseFile -Label "GPL license"
Assert-FileExists -Path $VersionFile -Label "Windows version metadata"
Assert-DirectoryExists -Path $ResourcesDir -Label "resources directory"
Assert-FileExists `
    -Path (Join-Path $ResourcesDir "icon\icon.ico") `
    -Label "application icon"

$RequiredButtonIcons = @(
    "check.png",
    "copy.png",
    "delete.png",
    "details.png",
    "exit.png",
    "folder.png",
    "glass.png",
    "history.png",
    "info.png",
    "link.png",
    "load.png",
    "refresh.png",
    "save.png",
    "steamwm.png"
)

foreach ($IconName in $RequiredButtonIcons) {
    Assert-FileExists `
        -Path (Join-Path $ResourcesDir "icon\buttons\$IconName") `
        -Label "button icon $IconName"
}

if (-not $SkipDependencyInstall) {
    Write-Host "Installing/verifying build dependencies..." -ForegroundColor Cyan
    & $PythonCommand -m pip install --upgrade pyinstaller Pillow

    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Cleaning previous build output..." -ForegroundColor Cyan

foreach ($Path in @($BuildDir, $DistDir, $ReleaseDir, $ZipPath, $ChecksumPath)) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

Write-Host "Running PyInstaller..." -ForegroundColor Cyan
& $PythonCommand -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistDir `
    --workpath $BuildDir `
    $SpecFile

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$PackagedDir = Join-Path $DistDir "Meccha Mod Builder"
$PackagedExe = Join-Path $PackagedDir "Meccha Mod Builder.exe"

Assert-DirectoryExists -Path $PackagedDir -Label "packaged application directory"
Assert-FileExists -Path $PackagedExe -Label "packaged executable"

Write-Host "Preparing release directory..." -ForegroundColor Cyan
Copy-Item -LiteralPath $PackagedDir -Destination $ReleaseDir -Recurse -Force

# Ensure documentation is visible at the release root even if PyInstaller also
# placed it in the collected application directory.
Copy-Item -LiteralPath $ReadmeFile -Destination (Join-Path $ReleaseDir "README.md") -Force
Copy-Item -LiteralPath $LicenseFile -Destination (Join-Path $ReleaseDir "LICENSE") -Force

Write-Host "Creating release archive..." -ForegroundColor Cyan
Compress-Archive `
    -LiteralPath $ReleaseDir `
    -DestinationPath $ZipPath `
    -CompressionLevel Optimal `
    -Force

$Hash = Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256
"$($Hash.Hash.ToLower())  $([System.IO.Path]::GetFileName($ZipPath))" |
    Set-Content -LiteralPath $ChecksumPath -Encoding ASCII

Write-Host ""
Write-Host "Release build complete." -ForegroundColor Green
Write-Host "Application folder: $ReleaseDir"
Write-Host "ZIP archive:        $ZipPath"
Write-Host "SHA-256 file:       $ChecksumPath"
Write-Host ""
Write-Host "Next: test the packaged executable from outside the repository." -ForegroundColor Yellow
