Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "::group::Installing Cinc Workstation v$env:CINC_VERSION"
Write-Host "channel=$env:CINC_CHANNEL"
Write-Host 'installer=https://omnitruck.cinc.sh/install.ps1'
. { Invoke-WebRequest -UseBasicParsing https://omnitruck.cinc.sh/install.ps1 } | Invoke-Expression
install -project cinc-workstation -channel $env:CINC_CHANNEL -version $env:CINC_VERSION
Write-Host '::endgroup::'
