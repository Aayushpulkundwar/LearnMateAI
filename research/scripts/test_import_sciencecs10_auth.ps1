$ErrorActionPreference = 'Stop'
$script = Get-Content (Join-Path $PSScriptRoot 'import_sciencecs10.ps1') -Raw
foreach ($required in @('Add-Type -AssemblyName System.Net.Http', '[Net.Http.HttpClientHandler]::new()', '$httpHandler.CookieContainer = $WebSession.Cookies', '[Net.Http.HttpClient]::new($httpHandler)')) {
  if (-not $script.Contains($required)) { throw "Missing authenticated upload safeguard: $required" }
}
if ($script.Contains("Headers.Add('Cookie'") -or $script.Contains('$headers.Cookie')) { throw 'Manual Cookie headers must not be used for multipart authentication.' }
Write-Output 'Authenticated multipart client regression check passed.'
