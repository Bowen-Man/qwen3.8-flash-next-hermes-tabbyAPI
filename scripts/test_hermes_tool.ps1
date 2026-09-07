$ErrorActionPreference = "Stop"

$token = [guid]::NewGuid().ToString()
$testFile = Join-Path $env:TEMP "hermes_tool_test.txt"

Set-Content -Path $testFile -Value $token -NoNewline

Write-Host "Test file: $testFile"
Write-Host "Expected UUID: $token"
Write-Host ""

$prompt = "You must use the file tool to read $testFile and return its contents exactly. Do not guess."

try {
    $output = (& hermes chat --oneshot --toolsets file -q $prompt 2>&1 | Out-String)
    Write-Host $output

    if ($output -match [regex]::Escape($token)) {
        Write-Host "PASS: Hermes executed the file tool and returned the unpredictable UUID."
        exit 0
    }

    Write-Host "FAIL: The expected UUID was not found in Hermes output."
    exit 1
}
finally {
    Remove-Item -Path $testFile -ErrorAction SilentlyContinue
}
