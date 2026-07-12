"""统一配置管理

优先级：环境变量 > .env 文件 > 硬编码默认值

使用示例：
    from config import settings
    proxy = settings.get_proxy_for("serper")
    client = httpx.AsyncClient(proxies=proxy, timeout=...)

代理说明：
    - 如果你的代理工具（Clash/V2Ray等）运行在本地 7890 端口，
      设置 export HTTP_PROXY=http://127.0.0.1:7890
    - 也可以单独为某个 API 设置代理：
      SERPER_PROXY_URL=http://127.0.0.1:7890
      DEEPSEEK_PROXY_URL=http://127.0.0.1:7890
      VOLC_PROXY_URL=http://127.0.0.1:7890
    - 不设置则直连（国内可访问的 API 不需要代理）
"""
import os
from dataclasses import dataclass, field
from typing import Any

# 优先从项目根目录的 .env 文件加载
_env_loaded = False
for _dotenv_path in [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),  # 项目根目录
    os.path.join(os.path.dirname(__file__), ".env"),                   # backend 目录
]:
    if os.path.isfile(_dotenv_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(_dotenv_path)
            _env_loaded = True
            break
        except ImportError:
            pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # ── API Keys ──
    serper_api_key: str = field(default_factory=lambda: _env("SERPER_API_KEY", ""))
    deepseek_api_key: str = field(
        default_factory=lambda: _env("DEEPSEEK_API_KEY")
    )
    volc_api_key: str = field(
        default_factory=lambda: _env("VOLC_API_KEY")
    )
    volc_model: str = field(
        default_factory=lambda: _env(
            "VOLC_MODEL",
            "ep-m-20260708201152-2zhwj",
        )
    )

    # ── API Base URLs ──
    deepseek_base_url: str = field(
        default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    volc_base_url: str = field(
        default_factory=lambda: _env(
            "VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
    )
    serper_search_url: str = "https://google.serper.dev/search"
    serper_image_url: str = "https://google.serper.dev/images"

    # ── Proxy 配置 ──
    # 全局代理（会被单独的 API 代理覆盖）
    http_proxy: str = field(default_factory=lambda: _env("HTTP_PROXY", ""))
    https_proxy: str = field(default_factory=lambda: _env("HTTPS_PROXY", ""))

    # 各 API 独立代理（优先级高于全局代理）
    serper_proxy: str = field(default_factory=lambda: _env("SERPER_PROXY_URL", ""))
    deepseek_proxy: str = field(default_factory=lambda: _env("DEEPSEEK_PROXY_URL", ""))
    volc_proxy: str = field(default_factory=lambda: _env("VOLC_PROXY_URL", ""))

    # ── 图像生成风格 ──
    # 该文案会被拼接到图像 prompt 末尾，控制画面风格
    # 可在 .env 中通过 IMAGE_GEN_STYLE 覆盖
    image_gen_style: str = field(
        default_factory=lambda: _env(
            "IMAGE_GEN_STYLE",
            "retro 16-bit pixel art, nostalgic game screenshot aesthetic, "
            "warm nostalgic color palette, visible pixel grid and crisp blocky edges, "
            "flat 2D shading with limited color count, SNES/GBA-era sprite art quality, "
            "no smooth gradients, no photorealistic detail, no 3D rendering",
        )
    )

    # ── 超时 ──
    search_timeout: int = 15
    image_gen_timeout: int = 120
    llm_timeout: int = 30
    download_timeout: int = 15

    # ── 阿里云 OSS 对象存储 ──
    oss_access_key_id: str = field(default_factory=lambda: _env("OSS_ACCESS_KEY_ID", ""))
    oss_access_key_secret: str = field(default_factory=lambda: _env("OSS_ACCESS_KEY_SECRET", ""))
    oss_endpoint: str = field(default_factory=lambda: _env("OSS_ENDPOINT", ""))
    oss_bucket_name: str = field(default_factory=lambda: _env("OSS_BUCKET_NAME", ""))
    oss_cdn_domain: str = field(default_factory=lambda: _env("OSS_CDN_DOMAIN", ""))

    # ── 认证 ──
    secret_key: str = field(
        default_factory=lambda: _env("SECRET_KEY", "change-me-in-production-please-use-a-real-secret")
    )
    token_expire_minutes: int = field(
        default_factory=lambda: int(_env("TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
    )

    def get_proxy_for(self, service: str) -> str | None:
        """获取指定服务的代理 URL

        参数:
            service: "serper" | "deepseek" | "volc"

        返回:
            代理 URL 字符串（如 "http://127.0.0.1:7890"），或 None（直连）
        """
        service_map: dict[str, str] = {
            "serper": self.serper_proxy,
            "deepseek": self.deepseek_proxy,
            "volc": self.volc_proxy,
        }
        specific = service_map.get(service, "")
        return specific or self.http_proxy or self.https_proxy or None

    def should_proxy(self, service: str) -> bool:
        """判断某个服务是否需要配置代理"""
        return bool(self.get_proxy_for(service))


settings = Settings()
