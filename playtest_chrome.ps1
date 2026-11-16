# Start a Chrome only for playtests: its own profile, DevTools on 9333, never the shared AI Chrome on 9222.
# Runs only in a separate Chrome profile/port, and not while someone is using this PC.
# Usage: powershell -NoProfile -File playtest_chrome.ps1 [-Port 9333] [-Stop]
param([int]$Port = 9333, [switch]$Stop)
$ErrorActionPreference = 'Stop'
$profileDir = Join-Path $env:LOCALAPPDATA 'jev_playtest_chrome'
if ($Port -eq 9222) { throw 'port 9222 is the shared AI Chrome: pick another port' }
$mine = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -like "*$profileDir*" }
if ($Stop) {
    $mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
    "PLAYTEST_CHROME_STOPPED $($mine.Count)"
    return
}
try {
    $v = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
    "PLAYTEST_CHROME_ALREADY $Port $($v.Browser)"
    return
} catch { }
$exe = @('C:\Program Files\Google\Chrome\Application\chrome.exe',
         'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
         "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { throw 'chrome.exe not found' }
Start-Process $exe -ArgumentList @("--remote-debugging-port=$Port", "--user-data-dir=`"$profileDir`"",
    '--no-first-run', '--no-default-browser-check', '--window-position=0,0', '--window-size=1200,900', 'about:blank')
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try { $v = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 2; "PLAYTEST_CHROME_OK $Port $($v.Browser)"; return } catch { }
}
throw "Chrome did not open DevTools on $Port"
