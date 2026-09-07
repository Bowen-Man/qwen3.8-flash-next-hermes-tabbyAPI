<#
.SYNOPSIS
    End-to-end Hermes file-tool integration test.

.DESCRIPTION
    This script verifies the complete local Agent tool-calling chain:

        Hermes Agent
          -> OpenAI-compatible endpoint
          -> model emits a structured tool call
          -> Hermes executes the file tool
          -> tool result returns to the model
          -> model returns the unpredictable UUID

    The script also sets a Qwen3.8-compatible Hermes reasoning effort before
    testing. Qwen3.8 currently expects: low, medium, or xhigh.

    By default the selected reasoning effort is kept in Hermes config after
    the test, because "none" can cause HTTP 400 with the Qwen3.8 template.

.PARAMETER ReasoningEffort
    Hermes reasoning effort used for the test.
    Allowed values: low, medium, xhigh.
    Default: medium.

.PARAMETER RestoreReasoning
    Restore the previous Hermes reasoning_effort after the test.

.PARAMETER ShowHermesOutput
    Print the complete Hermes terminal output.
    Normally hidden on PASS to avoid noisy Rich/Unicode terminal rendering,
    especially under Windows PowerShell 5.1.

.PARAMETER KeepTestFile
    Keep the temporary UUID file instead of deleting it.

.EXAMPLE
    .\scripts\test_hermes_tool.ps1

.EXAMPLE
    .\scripts\test_hermes_tool.ps1 -ReasoningEffort low

.EXAMPLE
    .\scripts\test_hermes_tool.ps1 -ReasoningEffort xhigh -ShowHermesOutput

.EXAMPLE
    .\scripts\test_hermes_tool.ps1 -RestoreReasoning
#>

[CmdletBinding()]
param(
    [ValidateSet("low", "medium", "xhigh")]
    [string]$ReasoningEffort = "medium",

    [switch]$RestoreReasoning,
    [switch]$ShowHermesOutput,
    [switch]$KeepTestFile
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# UTF-8 handling
# ---------------------------------------------------------------------------
# Hermes uses Unicode/Rich terminal output. Windows PowerShell 5.1 may decode
# native-process output using the legacy console code page, producing mojibake
# such as "鈹€" or "馃摉". These settings improve UTF-8 handling.
$originalConsoleOutputEncoding = [Console]::OutputEncoding
$originalConsoleInputEncoding  = [Console]::InputEncoding
$originalOutputEncoding        = $OutputEncoding
$originalPythonUtf8            = $env:PYTHONUTF8
$originalPythonIoEncoding      = $env:PYTHONIOENCODING
$originalCodePage              = [Console]::OutputEncoding.CodePage

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

try {
    [Console]::OutputEncoding = $utf8NoBom
    [Console]::InputEncoding  = $utf8NoBom
    $OutputEncoding           = $utf8NoBom

    # Hermes Agent runs on Python. Force its stdio to UTF-8 as well.
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    # Windows PowerShell 5.1 still relies partly on the active console code page.
    if ($PSVersionTable.PSEdition -eq "Desktop") {
        & chcp.com 65001 *> $null
    }

    # -----------------------------------------------------------------------
    # Pre-flight checks
    # -----------------------------------------------------------------------
    if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) {
        throw "Hermes CLI was not found in PATH. Run 'hermes --version' to verify the installation."
    }

    Write-Host "Hermes tool integration test"
    Write-Host "----------------------------"

    # -----------------------------------------------------------------------
    # Reasoning effort
    # -----------------------------------------------------------------------
    $previousReasoning = $null

    try {
        $previousReasoning = (
            & hermes config get agent.reasoning_effort 2>$null |
            Out-String
        ).Trim()
    }
    catch {
        # Older Hermes versions may behave differently here. We still try to
        # set and verify the requested value below.
        $previousReasoning = $null
    }

    Write-Host "Reasoning effort: $ReasoningEffort"

    # Hermes v0.21.x may emit a cosmetic "unrecognized config key" warning
    # even though agent.reasoning_effort is persisted and consumed at runtime.
    # Suppress that warning here, then verify the stored value explicitly.
    & hermes config set agent.reasoning_effort $ReasoningEffort *> $null

    $effectiveReasoning = (
        & hermes config get agent.reasoning_effort 2>$null |
        Out-String
    ).Trim()

    if ($effectiveReasoning -ne $ReasoningEffort) {
        throw "Failed to set Hermes reasoning effort. Expected '$ReasoningEffort', got '$effectiveReasoning'."
    }

    # -----------------------------------------------------------------------
    # Create unpredictable test data
    # -----------------------------------------------------------------------
    $token = [guid]::NewGuid().ToString()
    $testFile = Join-Path $env:TEMP "hermes_tool_test.txt"

    # Explicit UTF-8 without BOM. UUID itself is ASCII, but this keeps the file
    # format deterministic across PowerShell versions.
    [System.IO.File]::WriteAllText($testFile, $token, $utf8NoBom)

    Write-Host "Test file:        $testFile"
    Write-Host "Expected UUID:    $token"
    Write-Host ""

    $prompt = @"
You must use the file tool to read this file:

$testFile

Return the file contents exactly.
Do not guess the contents and do not fabricate a value.
"@

    # -----------------------------------------------------------------------
    # Run Hermes
    # -----------------------------------------------------------------------
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    $hermesOutput = (
        & hermes chat --oneshot --toolsets file -q $prompt 2>&1 |
        Out-String
    )

    $hermesExitCode = $LASTEXITCODE
    $stopwatch.Stop()

    if ($ShowHermesOutput) {
        Write-Host "----- Hermes output -----"
        Write-Host $hermesOutput
        Write-Host "-------------------------"
        Write-Host ""
    }

    # -----------------------------------------------------------------------
    # Validate
    # -----------------------------------------------------------------------
    $found = $hermesOutput -match [regex]::Escape($token)

    if ($hermesExitCode -eq 0 -and $found) {
        Write-Host "PASS"
        Write-Host "Hermes executed the file-tool workflow and returned the unpredictable UUID."
        Write-Host ("Elapsed:          {0:N2} s" -f $stopwatch.Elapsed.TotalSeconds)
        Write-Host "Observed UUID:    $token"
        exit 0
    }

    Write-Host "FAIL"
    Write-Host "Expected UUID was not confirmed in a successful Hermes response."
    Write-Host "Hermes exit code: $hermesExitCode"
    Write-Host ""

    # Always expose the full output on failure because it usually contains the
    # useful HTTP/provider/template error.
    if (-not $ShowHermesOutput) {
        Write-Host "----- Hermes output -----"
        Write-Host $hermesOutput
        Write-Host "-------------------------"
    }

    exit 1
}
finally {
    # Remove temporary file unless explicitly requested otherwise.
    if (-not $KeepTestFile -and $testFile) {
        Remove-Item -Path $testFile -ErrorAction SilentlyContinue
    }

    # Optional config restoration. Default behavior intentionally keeps the
    # tested Qwen3.8-compatible effort so subsequent Hermes calls keep working.
    if ($RestoreReasoning -and $previousReasoning) {
        try {
            & hermes config set agent.reasoning_effort $previousReasoning *> $null
        }
        catch {
            Write-Warning "Could not restore previous reasoning_effort '$previousReasoning'."
        }
    }

    # Restore process-local encoding/environment settings.
    try {
        [Console]::OutputEncoding = $originalConsoleOutputEncoding
        [Console]::InputEncoding  = $originalConsoleInputEncoding
        $OutputEncoding           = $originalOutputEncoding

        $env:PYTHONUTF8 = $originalPythonUtf8
        $env:PYTHONIOENCODING = $originalPythonIoEncoding

        if ($PSVersionTable.PSEdition -eq "Desktop" -and $originalCodePage) {
            & chcp.com $originalCodePage *> $null
        }
    }
    catch {
        # Do not mask the actual test result if terminal restoration fails.
    }
}
