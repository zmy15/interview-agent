"""上传记录存储服务 — JSON 文件持久化"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.schemas import UploadRecord

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads.json")


class UploadStore:
    """上传记录 JSON 存储，线程安全（双重检查锁单例）"""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, file_path: str = DEFAULT_PATH):
        # 双重检查锁 — 确保线程安全的单例
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, file_path: str = DEFAULT_PATH):
        if self._initialized:
            return
        with self._instance_lock:
            # 二次确认：可能被另一个线程初始化了
            if self._initialized:
                return
            self._initialized = True
            self._file_path = file_path
            self._data_lock = threading.Lock()
            self._data: dict = {"uploads": {}}
            self._load()

    def _load(self):
        """从 JSON 文件加载数据"""
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {"uploads": {}}
        else:
            self._data = {"uploads": {}}
            self._save()

    def _save(self):
        """保存数据到 JSON 文件"""
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def create(
        self,
        filename: str,
        upload_type: str,
        text: str,
        file_count: int = 1,
        tech_stack: Optional[list[str]] = None,
    ) -> UploadRecord:
        """创建上传记录"""
        with self._data_lock:
            upload_id = str(uuid.uuid4())[:8]
            now = datetime.now(timezone.utc).isoformat()
            # 生成文本预览（前200字符）
            preview = text[:200].replace("\n", " ").strip()
            if len(text) > 200:
                preview += "..."

            record = {
                "id": upload_id,
                "filename": filename,
                "type": upload_type,
                "text": text,
                "preview": preview,
                "file_count": file_count,
                "tech_stack": tech_stack or [],
                "created_at": now,
            }
            self._data["uploads"][upload_id] = record
            self._save()
            return UploadRecord(**record)

    def get(self, upload_id: str) -> Optional[UploadRecord]:
        """查询单条记录"""
        with self._data_lock:
            rec = self._data["uploads"].get(upload_id)
            return UploadRecord(**rec) if rec else None

    def list_all(self, upload_type: Optional[str] = None) -> list[UploadRecord]:
        """列出所有记录，可按类型过滤"""
        with self._data_lock:
            records = list(self._data["uploads"].values())
            if upload_type:
                records = [r for r in records if r["type"] == upload_type]
            # 按时间倒序
            records.sort(key=lambda r: r["created_at"], reverse=True)
            return [UploadRecord(**r) for r in records]

    def delete(self, upload_id: str) -> bool:
        """删除记录"""
        with self._data_lock:
            if upload_id not in self._data["uploads"]:
                return False
            del self._data["uploads"][upload_id]
            self._save()
            return True

    def delete_all(self, upload_type: Optional[str] = None) -> int:
        """删除所有记录（或按类型），返回删除数量"""
        with self._data_lock:
            if upload_type:
                to_delete = [
                    k for k, v in self._data["uploads"].items()
                    if v["type"] == upload_type
                ]
            else:
                to_delete = list(self._data["uploads"].keys())
            for k in to_delete:
                del self._data["uploads"][k]
            self._save()
            return len(to_delete)
