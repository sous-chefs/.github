Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The MSI updates the registry PATH but not the current session.
$machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
$env:PATH = "$machinePath;$userPath"

$cincBin = (Get-Command cinc -ErrorAction SilentlyContinue)?.Source |
  Split-Path -Parent

if ($cincBin) {
  Write-Host "Adding Cinc bin directory to GITHUB_PATH: $cincBin"
  $cincBin | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
} else {
  Write-Host 'Cinc command was not found while refreshing PATH.'
}
