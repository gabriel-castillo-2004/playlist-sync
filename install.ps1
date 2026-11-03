# Playlist Sync — Instalador para Windows PowerShell
$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Playlist Sync — Instalador para Windows" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Verificar Python 3.12
Write-Host "[1/5] Verificando Python..." -ForegroundColor Yellow
$pythonExe = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
    $pythonArgs = @("-3.12")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
}

if (-not $pythonExe) {
    Write-Host "Python no detectado. Instalando Python 3.12 mediante winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements
    $pythonExe = "python"
}

# 2. Verificar ffmpeg
Write-Host "[2/5] Verificando ffmpeg..." -ForegroundColor Yellow
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ffmpeg no detectado. Instalando mediante winget..." -ForegroundColor Yellow
    winget install --id Gyan.FFmpeg --exact --source winget --accept-package-agreements --accept-source-agreements
    Write-Host "Aviso: Puede requerir reiniciar la terminal para actualizar el PATH." -ForegroundColor Gray
}

# 3. Verificar Deno
Write-Host "[3/5] Verificando runtime Deno..." -ForegroundColor Yellow
if (-not (Get-Command deno -ErrorAction SilentlyContinue)) {
    Write-Host "Deno no detectado. Instalando mediante winget..." -ForegroundColor Yellow
    winget install --id DenoLand.Deno --exact --source winget --accept-package-agreements --accept-source-agreements
}

# 4. Crear venv e instalar dependencias
Write-Host "[4/5] Configurando entorno virtual (.venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    & $pythonExe @pythonArgs -m venv .venv
}

$venvPython = ".\.venv\Scripts\python.exe"
$venvPip = ".\.venv\Scripts\pip.exe"

& $venvPip install --upgrade pip
& $venvPip install -e ".[dev]"

# 5. Ejecutar diagnóstico
Write-Host "[5/5] Ejecutando verificación del sistema (doctor)..." -ForegroundColor Yellow
& $venvPython -m playlist_sync.doctor

Write-Host "`nInstalación completada. Puedes iniciar la aplicación con .\start.bat" -ForegroundColor Green

