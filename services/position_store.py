"""岗位存储服务 — JSON 文件持久化"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from models.schemas import PositionResponse, JDResponse
from utils.position_classifier import classify_position

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "positions.json")


class PositionStore:
    """岗位 JSON 存储，线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, file_path: str = DEFAULT_PATH):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, file_path: str = DEFAULT_PATH):
        if self._initialized:
            return
        self._initialized = True
        self._file_path = file_path
        self._lock = threading.Lock()
        self._data: dict = {"positions": {}}
        self._load()

    def _load(self):
        """从 JSON 文件加载数据"""
        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {"positions": {}}
        else:
            self._data = {"positions": {}}
            self._save()

    def _save(self):
        """保存数据到 JSON 文件"""
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def create(self, name: str, description: str = "") -> PositionResponse:
        """创建岗位"""
        with self._lock:
            if name in self._data["positions"]:
                raise ValueError(f"岗位 '{name}' 已存在")
            now = datetime.now(timezone.utc).isoformat()
            self._data["positions"][name] = {
                "name": name,
                "description": description,
                "position_type": classify_position(name),
                "jds": [],
                "created_at": now,
                "updated_at": now,
            }
            self._save()
            return self._to_response(self._data["positions"][name])

    def get(self, name: str) -> Optional[PositionResponse]:
        """查询单个岗位"""
        with self._lock:
            pos = self._data["positions"].get(name)
            return self._to_response(pos) if pos else None

    def list_all(self) -> list[PositionResponse]:
        """列出所有岗位"""
        with self._lock:
            return [self._to_response(p) for p in self._data["positions"].values()]

    def update(self, name: str, description: str) -> Optional[PositionResponse]:
        """更新岗位描述"""
        with self._lock:
            pos = self._data["positions"].get(name)
            if not pos:
                return None
            pos["description"] = description
            pos["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
            return self._to_response(pos)

    def delete(self, name: str) -> bool:
        """删除岗位"""
        with self._lock:
            if name not in self._data["positions"]:
                return False
            del self._data["positions"][name]
            self._save()
            return True

    def add_jd(self, position_name: str, content: str) -> Optional[JDResponse]:
        """为岗位添加 JD"""
        with self._lock:
            pos = self._data["positions"].get(position_name)
            if not pos:
                return None
            jd = {
                "id": str(uuid.uuid4()),
                "content": content,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            pos["jds"].append(jd)
            pos["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
            return JDResponse(**jd)

    def remove_jd(self, position_name: str, jd_id: str) -> bool:
        """删除指定 JD"""
        with self._lock:
            pos = self._data["positions"].get(position_name)
            if not pos:
                return False
            original_len = len(pos["jds"])
            pos["jds"] = [j for j in pos["jds"] if j["id"] != jd_id]
            if len(pos["jds"]) == original_len:
                return False
            pos["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
            return True

    def update_jd(self, position_name: str, jd_id: str, content: str) -> Optional[JDResponse]:
        """修改指定 JD"""
        with self._lock:
            pos = self._data["positions"].get(position_name)
            if not pos:
                return None
            for jd in pos["jds"]:
                if jd["id"] == jd_id:
                    jd["content"] = content
                    jd["created_at"] = datetime.now(timezone.utc).isoformat()
                    pos["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                    return JDResponse(**jd)
            return None

    @staticmethod
    def _to_response(pos: dict) -> PositionResponse:
        return PositionResponse(
            name=pos["name"],
            description=pos.get("description", ""),
            position_type=pos.get("position_type", "未知"),
            jds=[JDResponse(**j) for j in pos.get("jds", [])],
            created_at=pos.get("created_at", ""),
            updated_at=pos.get("updated_at", ""),
        )
