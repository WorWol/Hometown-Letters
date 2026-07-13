# ═══════════════════════════════════════════════════════════════
# 故乡来信 — Windows PowerShell 一键启动脚本
# ═══════════════════════════════════════════════════════════════
# 使用方法：
#   1. 右键点击 start.ps1 → "使用 PowerShell 运行"
#      或在 PowerShell 中执行：
#         .\start.ps1
#   2. 如果遇到执行策略限制，先运行：
#         Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
# 支持参数：
#   .\start.ps1 -Port 9090    # 指定端口
#   .\start.ps1 -SetupOnly    # 仅设置环境
# ═══════════════════════════════════════════════════════════════

param(
    [int]$Port = 8787,
    [string]$HostAddr = "0.0.0.0",
    [switch]$SetupOnly = $false,
    [switch]$SkipCheck = $false
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectDir "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$EnvFile = Join-Path $ProjectDir ".env"
$EnvExample = Join-Path $ProjectDir ".env.example"

# ── 颜色函数 ──
function Write-Green  { Write-Host $args -ForegroundColor Green }
function Write-Yellow { Write-Host $args -ForegroundColor Yellow }
function Write-Red    { Write-Host $args -ForegroundColor Red }
function Write-Cyan   { Write-Host $args -ForegroundColor Cyan }

# ── 横幅 ──
Write-Cyan "══════════════════════════════════════"
Write-Cyan "  故乡来信 — Hometown Letters"
Write-Cyan "  Windows 启动脚本"
Write-Cyan "══════════════════════════════════════"
Write-Host ""

# ── 1. 检查 Python ──
Write-Host "[…] 检查 Python..." -NoNewline
try {
    $pythonVersion = python --version 2>&1
    Write-Host " OK" -ForegroundColor Green
    Write-Green "[✓] $pythonVersion"
} catch {
    try {
        $pythonVersion = python3 --version 2>&1
        Write-Host " OK" -ForegroundColor Green
        Write-Green "[✓] $pythonVersion"
    } catch {
        Write-Red "[✗] 未找到 Python！请安装 Python 3.10+"
        Write-Red "    下载地址: https://www.python.org/downloads/"
        Write-Red "    ⚠ 安装时勾选 'Add Python to PATH'"
        exit 1
    }
}

# ── 2. 虚拟环境 ──
$pythonExe = Join-Path $VenvDir "Scripts" "python.exe"
$pipExe = Join-Path $VenvDir "Scripts" "pip.exe"

if (Test-Path $pythonExe) {
    Write-Green "[✓] 虚拟环境已存在: $VenvDir"
} else {
    Write-Yellow "[!] 未检测到虚拟环境，正在创建..."
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Red "[✗] 虚拟环境创建失败"
        exit 1
    }
    Write-Green "[✓] 虚拟环境创建成功"
}

# ── 3. 安装依赖 ──
Write-Cyan "[…] 安装依赖..."
$requirementsFile = Join-Path $BackendDir "requirements.txt"
& $pipExe install -r $requirementsFile 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Red "[✗] 依赖安装失败，正在重试（显示详细输出）..."
    & $pipExe install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Red "[✗] 依赖安装失败"
        exit 1
    }
}
Write-Green "[✓] 依赖安装完成"

# ── 4. 检查 .env ──
if (-not $SkipCheck) {
    if (Test-Path $EnvFile) {
        Write-Green "[✓] 发现 .env 文件"
    } else {
        Write-Yellow "[!] 未找到 .env 文件"
        if (Test-Path $EnvExample) {
            Copy-Item $EnvExample $EnvFile
            Write-Yellow "    已从 .env.example 复制模板"
            Write-Yellow "    请编辑 .env 文件填入 API Key 后重新运行"
        }
    }
}

# ── 5. 启动 ──
if ($SetupOnly) {
    Write-Host ""
    Write-Green "[✓] 环境设置完成！"
    Write-Green "    虚拟环境: $VenvDir"
    Write-Green "    激活命令: $VenvDir\Scripts\activate"
    Write-Green "    启动命令: .\start.ps1"
    exit 0
}

Write-Host ""
Write-Cyan "── 启动后端服务 ──"
Write-Green "[✓] 服务地址: http://${HostAddr}:${Port}"
Write-Green "[✓] API 文档: http://${HostAddr}:${Port}/docs"
if ($HostAddr -eq "0.0.0.0") {
    Write-Green "[✓] 本地访问: http://localhost:${Port}"
}
Write-Cyan "══════════════════════════════════════"
Write-Yellow "  按 Ctrl+C 停止服务"
Write-Host ""

Set-Location $BackendDir
& $pythonExe -m uvicorn main:app --host $HostAddr --port $Port --reload

# 如果 uvicorn 退出
Set-Location $ProjectDir
