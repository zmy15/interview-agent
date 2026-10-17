"""用户 API Key 的对称加密 —— Fernet（AES-128-CBC + HMAC-SHA256）

为什么需要这个模块
------------------
用户填写的 DeepSeek API Key 原先只存在浏览器 localStorage 里。桌面版用的是
pywebview 的 native 窗口，而 ``webview.start()`` 的 ``private_mode`` 默认为
True —— WebView2 使用临时配置目录，窗口一关 localStorage 就没了，于是
「重启之后密钥就不见了」。

把密钥加密后存进数据库可以让它：
  * 重启 / 换窗口实现（native、浏览器 --app）都不丢；
  * 不随 localStorage 一起按「协议+域名+端口」隔离，换端口也能读到；
  * 不出现在浏览器配置目录里。

安全边界（务必如实理解）
------------------------
这是一层「静态加密」：防止数据库文件被单独拷走、备份泄露或被误提交时
直接读到明文密钥。它**不能**抵御同时拿到数据库与解密密钥（.env 或
data/.encryption_key）的攻击者 —— 那种情况下密钥本就必须能被应用解出来。

密钥来源优先级
--------------
1. 环境变量 / .env 中的 ``APP_ENCRYPTION_KEY``
2. ``data/.encryption_key`` 文件（.env 不可写时的落地点）
3. 都没有则**自动生成**：优先写回 .env，同时也在 data/ 留一份

轮换警告：改动上述任一来源都会导致已存储的密文无法解密，用户需重新录入。
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# 项目根目录（services/ 的上一级）
_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"
_KEY_FILE = _ROOT / "data" / ".encryption_key"

# 惰性初始化的 Fernet 实例。刻意不在导入时创建 —— 否则仅「导入本模块」
# 就会往 .env 写密钥，而多数进程（如只读的 API 进程）根本用不上它。
_fernet: Optional[Fernet] = None


# ══════════════════════════════════════════════════════════════
# 密钥的获取 / 生成
# ══════════════════════════════════════════════════════════════


def _is_valid_key(value: str) -> bool:
    """Fernet 要求 urlsafe-base64 编码的 32 字节密钥；构造成功即为合法"""
    if not value:
        return False
    try:
        Fernet(value.encode("utf-8"))
        return True
    except Exception:
        return False


def _append_to_env(key: str) -> bool:
    """把生成的密钥追加到 .env，成功返回 True

    只追加、不重写整个文件：.env 里通常还有用户自己的配置与注释，
    整文件重写容易破坏格式或丢注释。
    """
    try:
        if not _ENV_FILE.exists():
            return False
        prefix = "" if _ENV_FILE.stat().st_size == 0 else "\n"
        with _ENV_FILE.open("a", encoding="utf-8") as fh:
            fh.write(prefix)
            fh.write("# 由应用自动生成：用于加密存储用户的 API Key。\n")
            fh.write("# ⚠ 删除或修改该值会导致已保存的 API Key 无法解密。\n")
            fh.write(f"APP_ENCRYPTION_KEY={key}\n")
        return True
    except OSError as exc:
        logger.warning("无法写入 .env（%s），密钥将只保存到 %s", exc, _KEY_FILE)
        return False


def _write_key_file(key: str) -> None:
    """把密钥落到 data/.encryption_key（尽力收紧权限）"""
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows 上 chmod 语义有限，失败不必影响功能
        pass


def _load_or_create_key() -> str:
    """按 环境变量 → 密钥文件 → 新生成 的顺序拿到一个合法 Fernet 密钥"""

    # 1) 显式配置（.env 由 config.py 的 load_dotenv 提前载入 os.environ）
    env_key = (os.getenv("APP_ENCRYPTION_KEY") or "").strip()
    if env_key:
        if _is_valid_key(env_key):
            return env_key
        # 配置了但格式非法：直接报错，好过静默换新密钥导致旧密文全部解不开
        raise RuntimeError(
            "APP_ENCRYPTION_KEY 不是合法的 Fernet 密钥（应为 urlsafe-base64 的 32 字节）。"
            "请删除该项让应用自动重新生成，或手动执行 "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" 生成。"
        )

    # 2) 之前落盘的密钥文件
    if _KEY_FILE.exists():
        try:
            file_key = _KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("读取 %s 失败：%s", _KEY_FILE, exc)
            file_key = ""
        if _is_valid_key(file_key):
            return file_key
        if file_key:
            logger.warning("%s 中的密钥格式非法，将重新生成", _KEY_FILE)

    # 3) 首次使用：生成并尽量持久化
    new_key: str = Fernet.generate_key().decode("utf-8")
    wrote_env = _append_to_env(new_key)
    try:
        _write_key_file(new_key)
    except OSError as exc:
        logger.warning("无法写入 %s：%s", _KEY_FILE, exc)
    logger.info(
        "🔐 已生成 API Key 加密密钥（保存到 %s）。请勿在轮换时丢失该密钥。",
        ".env" if wrote_env else str(_KEY_FILE),
    )
    return new_key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key().encode("utf-8"))
    return _fernet


# ══════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════


def encrypt(plaintext: str) -> str:
    """加密明文，返回可直接入库的 ASCII 密文"""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> Optional[str]:
    """解密密文；密钥不匹配或数据损坏时返回 None（不抛异常）"""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error(
            "API Key 解密失败：APP_ENCRYPTION_KEY 可能已变更，需要重新录入 API Key"
        )
        return None
    except Exception as exc:  # noqa: BLE001 - 解密失败不应让整个请求 500
        logger.error("API Key 解密异常: %s", exc)
        return None


def mask(plaintext: str) -> str:
    """把密钥掩码成可安全展示的形式：sk-6680…d69d

    与前端此前的展示格式保持一致（头 6 位 + 尾 4 位）。
    过短的密钥整体打码，避免把完整密钥又暴露出去。
    """
    key = (plaintext or "").strip()
    if not key:
        return ""
    if len(key) <= 12:
        return "•" * len(key)
    return f"{key[:6]}…{key[-4:]}"
