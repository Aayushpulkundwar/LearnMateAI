function ConvertTo-ResearchProcessArgument([string]$Value) {
  # Quote every argument using the Windows CRT command-line escaping rules.
  $builder = New-Object System.Text.StringBuilder
  [void]$builder.Append('"')
  $slashes = 0
  foreach ($character in $Value.ToCharArray()) {
    if ($character -eq [char]92) {
      $slashes++
      continue
    }
    if ($character -eq [char]34) {
      [void]$builder.Append(('\' * (2 * $slashes + 1)))
      [void]$builder.Append('"')
      $slashes = 0
      continue
    }
    if ($slashes -gt 0) { [void]$builder.Append(('\' * $slashes)); $slashes = 0 }
    [void]$builder.Append($character)
  }
  if ($slashes -gt 0) { [void]$builder.Append(('\' * (2 * $slashes))) }
  [void]$builder.Append('"')
  return $builder.ToString()
}

function Invoke-ResearchProcess {
  param(
    [Parameter(Mandatory=$true)][string[]]$DockerArguments,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [string]$Executable = 'docker'
  )

  $stdoutPath = Join-Path ([IO.Path]::GetTempPath()) ("learnmate-docker-$([Guid]::NewGuid().ToString('N')).stdout")
  $stderrPath = Join-Path ([IO.Path]::GetTempPath()) ("learnmate-docker-$([Guid]::NewGuid().ToString('N')).stderr")
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $Executable
  $startInfo.Arguments = (($DockerArguments | ForEach-Object { ConvertTo-ResearchProcessArgument ([string]$_) }) -join ' ')
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $startInfo

  try {
    if (-not $process.Start()) { throw "Could not start $Executable." }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.Result
    $stderr = $stderrTask.Result
    [IO.File]::WriteAllText($stdoutPath, $stdout, (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($stderrPath, $stderr, (New-Object System.Text.UTF8Encoding($false)))

    if ($stdout.Length -gt 0) {
      Add-Content -LiteralPath $LogPath -Value "[stdout] $stdout" -Encoding UTF8
      Write-Host $stdout -NoNewline
    }
    if ($stderr.Length -gt 0) {
      Add-Content -LiteralPath $LogPath -Value "[stderr] $stderr" -Encoding UTF8
      Write-Host $stderr -NoNewline
    }
    if ($process.ExitCode -ne 0) {
      throw "$Executable failed with exit code $($process.ExitCode); see $LogPath."
    }
  }
  finally {
    $process.Dispose()
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
  }
}
