Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-CommandPath {
  param([string] $Name)

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  return ''
}

function Add-ActionOutput {
  param(
    [string] $Name,
    [string] $Value
  )

  "$Name=$Value" | Out-File -FilePath $env:GITHUB_OUTPUT -Encoding utf8 -Append
}

function Resolve-ExecutableVersion {
  param([string] $Path)

  $versionOutput = & $Path --version 2>&1
  if ($LASTEXITCODE -ne 0) {
    $versionOutput = & $Path version 2>&1
  }

  $version = $versionOutput |
    ForEach-Object { $_.ToString() } |
    Where-Object { $_ -and $_ -ne 'Redirecting to cinc' } |
    Select-Object -First 1

  if (-not $version) {
    Write-Error "Could not resolve $executable version."
    exit 1
  }

  return $version
}

$cincPath = Resolve-CommandPath -Name cinc
$chefPath = Resolve-CommandPath -Name chef
$knifePath = Resolve-CommandPath -Name knife

switch ($env:CINC_DISTRIBUTION) {
  'workstation' {
    if ($chefPath) {
      $executable = 'chef'
      $executablePath = $chefPath
    } else {
      $executable = 'cinc'
      $executablePath = $cincPath
    }
  }
  default {
    Write-Error "Unsupported distribution for Windows output resolution: $env:CINC_DISTRIBUTION"
    exit 1
  }
}

if (-not $executablePath) {
  Write-Error "$executable was not found in PATH."
  exit 1
}

$version = Resolve-ExecutableVersion -Path $executablePath

Write-Host '::group::Resolved Cinc action outputs'
Write-Host "distribution=$env:CINC_DISTRIBUTION"
Write-Host "executable=$executable"
Write-Host "executable_path=$executablePath"
Write-Host "cinc_path=$cincPath"
Write-Host "chef_path=$chefPath"
Write-Host "knife_path=$knifePath"
Write-Host "version=$version"

Add-ActionOutput -Name distribution -Value $env:CINC_DISTRIBUTION
Add-ActionOutput -Name executable -Value $executable
Add-ActionOutput -Name executable_path -Value $executablePath
Add-ActionOutput -Name cinc_path -Value $cincPath
Add-ActionOutput -Name chef_path -Value $chefPath
Add-ActionOutput -Name knife_path -Value $knifePath
Add-ActionOutput -Name version -Value $version
Write-Host '::endgroup::'
