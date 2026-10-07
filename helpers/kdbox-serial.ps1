# kdbox-serial.ps1 - talk to the box serial console from Windows PowerShell.
# Opens the port, optionally sends one line (-Cmd), and reads output for -Secs seconds.
# DtrEnable/RtsEnable are left false so an ESP32 bridge is not reset on open.
# Keep sent lines short; very long command lines can corrupt over the console.
param(
  [string]$Cmd  = "",
  [int]$Secs    = 4,
  [string]$Port = "COM4",
  [int]$Baud    = 115200,
  [int]$Tail    = 4000
)
try {
  $p = New-Object System.IO.Ports.SerialPort $Port,$Baud,None,8,([System.IO.Ports.StopBits]::One)
  $p.DtrEnable = $false
  $p.RtsEnable = $false
  $p.NewLine = "`n"
  $p.ReadTimeout = 400
  $p.Open()
  Start-Sleep -Milliseconds 250
  if ($Cmd -ne "") { $p.WriteLine($Cmd) }
  $sb = New-Object System.Text.StringBuilder
  $end = (Get-Date).AddSeconds($Secs)
  while ((Get-Date) -lt $end) {
    try { $s = $p.ReadExisting(); if ($s) { [void]$sb.Append($s) } } catch {}
    Start-Sleep -Milliseconds 120
  }
  $p.Close()
  $o = $sb.ToString()
  if ($o.Length -gt $Tail) { $o = "...[trimmed]...`n" + $o.Substring($o.Length - $Tail) }
  Write-Output $o
} catch {
  Write-Output "SERIAL-ERR: $_"
  try { if ($p -and $p.IsOpen) { $p.Close() } } catch {}
}
