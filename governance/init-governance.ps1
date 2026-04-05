param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,

    [Parameter(Mandatory = $true)]
    [string]$ProjectName,

    [string]$CurrentModule = "Module 0",
    [string]$CurrentTask = "Set session scope",
    [switch]$Force,
    [switch]$DryRun
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootstrap = Join-Path $scriptDir "bootstrap_governance.py"

if (-not (Test-Path $bootstrap)) {
    throw "bootstrap_governance.py not found at $bootstrap"
}

$args = @(
    $bootstrap,
    "--target", $TargetPath,
    "--project", $ProjectName,
    "--module", $CurrentModule,
    "--task", $CurrentTask
)

if ($Force) {
    $args += "--force"
}

if ($DryRun) {
    $args += "--dry-run"
}

python @args
