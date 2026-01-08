# ==============================================================================
# spectryn Chocolatey Uninstall Script
# ==============================================================================

$ErrorActionPreference = 'Stop'

$packageName = 'spectryn'

# Uninstall via pip
$pipArgs = @(
    'uninstall'
    '--yes'
    'spectryn'
)

# Try pip3 first, fall back to pip
$pipCommand = Get-Command pip3 -ErrorAction SilentlyContinue
if (-not $pipCommand) {
    $pipCommand = Get-Command pip -ErrorAction SilentlyContinue
}

if ($pipCommand) {
    Write-Host "Uninstalling $packageName using $($pipCommand.Source)..."
    & $pipCommand.Source $pipArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "$packageName uninstalled successfully" -ForegroundColor Green
    } else {
        Write-Warning "pip uninstall returned non-zero exit code"
    }
} else {
    Write-Warning "pip not found - $packageName may not be fully uninstalled"
}

