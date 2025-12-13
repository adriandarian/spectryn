# ==============================================================================
# md2jira Chocolatey Install Script
# ==============================================================================

$ErrorActionPreference = 'Stop'

$packageName = 'md2jira'
$version = '2.0.0'

# Install via pip (Python must be installed via dependency)
$pipArgs = @(
    'install'
    '--upgrade'
    "md2jira==$version"
)

# Try pip3 first, fall back to pip
$pipCommand = Get-Command pip3 -ErrorAction SilentlyContinue
if (-not $pipCommand) {
    $pipCommand = Get-Command pip -ErrorAction SilentlyContinue
}

if (-not $pipCommand) {
    throw "Python pip is required but not found. Please install Python 3.10+ first."
}

Write-Host "Installing $packageName v$version using $($pipCommand.Source)..."
& $pipCommand.Source $pipArgs

if ($LASTEXITCODE -ne 0) {
    throw "Failed to install $packageName via pip"
}

# Verify installation
$md2jiraPath = Get-Command md2jira -ErrorAction SilentlyContinue
if ($md2jiraPath) {
    Write-Host "$packageName installed successfully at: $($md2jiraPath.Source)" -ForegroundColor Green
} else {
    Write-Warning "$packageName installed but not found in PATH. You may need to restart your terminal."
}

Write-Host ""
Write-Host "To use md2jira, set these environment variables:" -ForegroundColor Cyan
Write-Host '  $env:JIRA_URL = "https://your-company.atlassian.net"'
Write-Host '  $env:JIRA_EMAIL = "your.email@company.com"'
Write-Host '  $env:JIRA_API_TOKEN = "your-api-token"'
Write-Host ""
Write-Host "Or add them permanently via System Properties > Environment Variables"

