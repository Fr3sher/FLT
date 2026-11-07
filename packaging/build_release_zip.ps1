#requires -Version 5.1
<#
.SYNOPSIS
  Build the supported Windows core ZIP from a committed source tree.
.DESCRIPTION
  No installed plugins or working files are copied. start.bat prepares Python
  on first launch. Commit the frontend Store build before making the archive.
#>
[CmdletBinding()]
param(
  [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$')]
  [string]$OutName = 'LoRA-Dataset-Studio-windows',
  [string]$SourceRef = 'HEAD',
  [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Builder = Join-Path $PSScriptRoot 'release_bundle.py'
$Arguments = @('-X', 'utf8', $Builder, '--repo', $Root, '--ref', $SourceRef, '--name', $OutName)
if ($env:RELEASE_TAG) { $Arguments += @('--tag', $env:RELEASE_TAG) }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'The committed core archive could not be built.' }
Write-Host 'Extract the ZIP, then double-click start.bat.'
