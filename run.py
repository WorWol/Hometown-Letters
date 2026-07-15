#!/usr/bin/env python3
"""
故乡来信 — 跨平台一键启动脚本
═══════════════════════════════════════════════════════════

支持 Mac / Windows / Linux，自动完成：
  1. 检查 Python 版本
  2. 创建虚拟环境（如不存在）
  3. 安装依赖
  4. 检查 .env 配置
  5. 启动服务（热重载）

使用方式：
  python run.py           # 一键启动
  python run.py --port 9090    # 指定端口
  python run.py --setup-only   # 仅创建 venv + 安装依赖，不启动

不需要安装 Docker。只要系统有 Python 3.10+ 即可。
═══════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path


# ── 常量 ──
PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_DIR / "backend"
VENV_DIR = BACKEND_DIR / ".venv"
ENV_FILE = PROJECT_DIR / ".env"
ENV_EXAMPLE_FILE = PROJECT_DIR / ".env.example"
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787

IS_WINDOWS = platform.system() == "Windows"

# ── 终端颜色 ──
if IS_WINDOWS:
    # Windows 下启用 ANSI 颜色支持
    os.system("")  # 开启 cmd 的 VT100 支持

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
NC = "\033[0m"  # No Color


def _python_exe() -> str:
    """返回虚拟环境中的 python 可执行文件路径"""
    if IS_WINDOWS:
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def _pip_exe() -> str:
    """返回虚拟环境中的 pip 可执行文件路径"""
    if IS_WINDOWS:
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def _activate_cmd() -> str:
    """返回激活虚拟环境的命令（仅用于提示）"""
    if IS_WINDOWS:
        return f"{VENV_DIR}\\Scripts\\activate"
    return f"source {VENV_DIR}/bin/activate"


def print_banner() -> None:
    """打印启动横幅"""
    print(f"{CYAN}══════════════════════════════════════{NC}")
    print(f"{CYAN}  故乡来信 — Hometown Letters{NC}")
    print(f"{CYAN}  跨平台启动脚本{NC}")
    print(f"{CYAN}══════════════════════════════════════{NC}")
    print(f"  系统: {platform.system()} {platform.release()}")
    print(f"  Python: {sys.version.split()[0]}")
    print()


def check_python() -> bool:
    """检查 Python 版本是否满足要求"""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        print(f"{RED}[✗] Python 版本过低: {major}.{minor}{NC}")
        print(f"{RED}    需要 Python 3.10+，请升级后重试{NC}")
        return False
    print(f"{GREEN}[✓] Python {major}.{minor} — 满足要求{NC}")
    return True


def setup_venv() -> bool:
    """创建虚拟环境（如不存在）"""
    if VENV_DIR.is_dir() and (_python_path := Path(_python_exe())).is_file():
        try:
            probe = subprocess.run(
                [str(_python_path), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode == 0:
                print(f"{GREEN}[✓] 虚拟环境已存在: {VENV_DIR}{NC}")
                return True
            print(f"{YELLOW}[!] 虚拟环境已损坏，正在重建...{NC}")
        except (OSError, subprocess.SubprocessError):
            print(f"{YELLOW}[!] 虚拟环境已损坏，正在重建...{NC}")

    else:
        print(f"{YELLOW}[!] 未检测到虚拟环境，正在创建...{NC}")
    try:
        venv.create(VENV_DIR, with_pip=True, clear=VENV_DIR.exists())
        print(f"{GREEN}[✓] 虚拟环境创建成功: {VENV_DIR}{NC}")
        return True
    except Exception as e:
        print(f"{RED}[✗] 虚拟环境创建失败: {e}{NC}")
        return False


def install_deps() -> bool:
    """安装/更新依赖"""
    if not REQUIREMENTS_FILE.is_file():
        print(f"{RED}[✗] 未找到 requirements.txt{NC}")
        return False

    print(f"{CYAN}[…] 安装依赖...{NC}")
    pip = _pip_exe()
    try:
        result = subprocess.run(
            [pip, "install", "-r", str(REQUIREMENTS_FILE)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            print(f"{GREEN}[✓] 依赖安装完成{NC}")
            return True
        else:
            # 打印最后几行错误
            lines = result.stderr.strip().split("\n")
            for line in lines[-5:]:
                print(f"  {RED}{line}{NC}")
            print(f"{RED}[✗] 依赖安装失败，请检查上方错误信息{NC}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{RED}[✗] 依赖安装超时（5分钟）{NC}")
        return False
    except FileNotFoundError:
        print(f"{RED}[✗] 未找到 pip: {pip}{NC}")
        print(f"{RED}    虚拟环境可能已损坏，请删除 {VENV_DIR} 后重试{NC}")
        return False


def check_env() -> bool:
    """检查 .env 文件是否存在并有必要的 API Key"""
    if ENV_FILE.is_file():
        print(f"{GREEN}[✓] 发现 .env 文件{NC}")
    else:
        print(f"{YELLOW}[!] 未找到 .env 文件{NC}")
        if ENV_EXAMPLE_FILE.is_file():
            print(f"{YELLOW}    正在从 .env.example 复制模板...{NC}")
            try:
                import shutil
                shutil.copy(ENV_EXAMPLE_FILE, ENV_FILE)
                print(f"{YELLOW}    已创建 .env 文件，请编辑填入 API Key 后重新运行{NC}")
                print(f"{YELLOW}    → {ENV_FILE}{NC}")
            except Exception as e:
                print(f"{RED}[✗] 无法创建 .env: {e}{NC}")
        return False

    # run.py 由系统 Python 执行，而依赖安装在虚拟环境中，
    # 因此这里不依赖 python-dotenv，只以 UTF-8 读取并检查关键项。
    try:
        content = ENV_FILE.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as e:
        print(f"{RED}[✗] 无法读取 .env: {e}{NC}")
        return False

    env_values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_values[key.strip()] = value.strip().strip("\"'")

    keys_to_check = {
        key: env_values.get(key, os.environ.get(key, ""))
        for key in ("DEEPSEEK_API_KEY", "SERPER_API_KEY", "VOLC_API_KEY")
    }
    missing = [
        k for k, v in keys_to_check.items()
        if not v or "your-" in v.lower() or "sk-your" in v.lower()
    ]
    if missing:
        print(f"{YELLOW}[!] 以下 API Key 未配置: {', '.join(missing)}{NC}")
        print(f"{YELLOW}    请编辑 .env 文件填入真实的 API Key{NC}")
        print(f"{YELLOW}    没有 API Key 也可以启动，但相关功能不可用{NC}")
    else:
        print(f"{GREEN}[✓] 关键 API Key 已配置{NC}")

    return True


def start_server(host: str, port: int) -> None:
    """启动 FastAPI 服务"""
    print()
    print(f"{CYAN}── 启动后端服务 ──{NC}")
    print(f"{GREEN}[✓] 服务地址: http://{host}:{port}{NC}")
    print(f"{GREEN}[✓] API 文档: http://{host}:{port}/docs{NC}")
    if host == "0.0.0.0":
        print(f"{GREEN}[✓] 局域网访问: http://localhost:{port}{NC}")
    print(f"{CYAN}══════════════════════════════════════{NC}")
    print(f"{YELLOW}  按 Ctrl+C 停止服务{NC}")
    print()

    python = _python_exe()
    os.chdir(BACKEND_DIR)

    cmd = [
        python, "-m", "uvicorn", "main:app",
        "--host", host,
        "--port", str(port),
        "--reload",
    ]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print()
        print(f"{GREEN}[✓] 服务已停止{NC}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[✗] 服务启动失败: {e}{NC}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="故乡来信 — 跨平台一键启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run.py                  # 一键启动（默认端口 8787）
  python run.py --port 9090      # 指定端口
  python run.py --setup-only     # 仅创建 venv + 安装依赖
  python run.py --skip-check     # 跳过 .env 检查
        """,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"服务端口（默认: {DEFAULT_PORT}）")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"绑定地址（默认: {DEFAULT_HOST}）")
    parser.add_argument("--setup-only", action="store_true", help="仅设置环境，不启动服务")
    parser.add_argument("--skip-check", action="store_true", help="跳过 .env 检查")
    args = parser.parse_args()

    print_banner()

    # 1. 检查 Python 版本
    if not check_python():
        sys.exit(1)

    # 2. 创建虚拟环境
    if not setup_venv():
        sys.exit(1)

    # 3. 安装依赖
    if not install_deps():
        sys.exit(1)

    # 4. 检查 .env
    if not args.skip_check:
        check_env()

    # 5. 启动 or 仅设置
    if args.setup_only:
        print(f"\n{GREEN}[✓] 环境设置完成！{NC}")
        print(f"{GREEN}    虚拟环境: {VENV_DIR}{NC}")
        print(f"{GREEN}    激活命令: {_activate_cmd()}{NC}")
        print(f"{GREEN}    启动命令: python run.py{NC}")
        return

    start_server(args.host, args.port)


if __name__ == "__main__":
    main()
