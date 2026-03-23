param(
    [switch]$NoVenv,
    [switch]$NoInno
)

$ErrorActionPreference = 'Stop'

$pythonExe = $null
$pythonPrefixArgs = @()

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    & $pythonExe @pythonPrefixArgs @Args
}

function Find-InnoSetupCompiler {
    $candidates = @(
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot

try {
    Write-Host "[1/4] Preparing Python environment..."

    if (-not $NoVenv) {
        if (-not (Test-Path '.venv\Scripts\python.exe')) {
            py -3 -m venv .venv
        }
        $pythonExe = Join-Path $repoRoot '.venv\\Scripts\\python.exe'
        $pythonPrefixArgs = @()
    } else {
        $pythonExe = 'py'
        $pythonPrefixArgs = @('-3')
    }

    Write-Host "[2/4] Installing build dependencies..."
    Invoke-Python -m pip install --upgrade pip
    Invoke-Python -m pip install -r requirements.txt pyinstaller pyinstaller-hooks-contrib

    Write-Host "[3/4] Building executable with PyInstaller..."
    Invoke-Python -m PyInstaller schoolbooth.spec --noconfirm

    if ($NoInno) {
        Write-Host "Skipping Inno Setup build because -NoInno was provided."
        Write-Host "Executable output should be in .\dist"
        exit 0
    }

    Write-Host "[4/4] Building Windows installer with Inno Setup..."
    $iscc = Find-InnoSetupCompiler
    if (-not $iscc) {
        throw "Inno Setup compiler (ISCC.exe) was not found. Install Inno Setup 6 and re-run."
    }

    & $iscc 'schoolbooth.iss'

    Write-Host "Build complete. Installer output is in .\output"
}
finally {
    Pop-Location
}
