"""向量存储服务 — FAISS + sentence-transformers（Windows 兼容）"""

import json
import logging
import os
import uuid
from typing import Optional

import numpy as np

from config import Settings

logger = logging.getLogger(__name__)

_VECTOR_STORE_AVAILABLE: Optional[bool] = None


def is_vector_store_available() -> bool:
    """检查向量存储依赖是否可用（sentence-transformers + faiss + numpy）"""
    global _VECTOR_STORE_AVAILABLE
    if _VECTOR_STORE_AVAILABLE is None:
        try:
            import torch  # noqa: F401
            import faiss  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401
            _VECTOR_STORE_AVAILABLE = True
        except (ImportError, OSError) as e:
            logger.warning(f"Vector store dependencies not available: {e}")
            _VECTOR_STORE_AVAILABLE = False
    return _VECTOR_STORE_AVAILABLE


class VectorStoreManager:
    """向量知识库管理器 — 基于 FAISS + sentence-transformers"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._embedding_model = None
        self._available = is_vector_store_available()
        self._collections: dict[str, dict] = {}  # 内存缓存：coll_name -> {index, docs, metas}
        self._index_dir = os.path.join(settings.CHROMA_PERSIST_PATH, "faiss_indexes")
        os.makedirs(self._index_dir, exist_ok=True)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def embedding_model(self):
        if not self._available:
            raise RuntimeError("Vector store is not available: sentence-transformers/torch not installed")
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self._settings.EMBEDDING_MODEL}")
            self._embedding_model = SentenceTransformer(self._settings.EMBEDDING_MODEL)
        return self._embedding_model

    @property
    def embedding_dim(self) -> int:
        """获取嵌入向量维度"""
        return self.embedding_model.get_embedding_dimension()

    # ========== 持久化辅助 ==========

    def _get_index_path(self, coll_name: str) -> str:
        return os.path.join(self._index_dir, f"{coll_name}.faiss")

    def _get_meta_path(self, coll_name: str) -> str:
        return os.path.join(self._index_dir, f"{coll_name}.json")

    def _sanitize_collection_name(self, name: str) -> str:
        """将岗位名称 sanitize 为合法的 collection 名称"""
        import re
        safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
        safe = safe.strip('_')
        if len(safe) < 3:
            safe = safe + "_kb"
        if len(safe) > 63:
            safe = safe[:63]
        return f"kb_{safe}"

    def _load_collection(self, coll_name: str):
        """从磁盘加载 collection 到内存缓存"""
        if coll_name in self._collections:
            return self._collections[coll_name]

        index_path = self._get_index_path(coll_name)
        meta_path = self._get_meta_path(coll_name)

        if os.path.exists(index_path) and os.path.exists(meta_path):
            import faiss
            index = faiss.read_index(index_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._collections[coll_name] = {
                "index": index,
                "docs": data.get("docs", []),
                "metas": data.get("metas", []),
            }
            return self._collections[coll_name]

        # 新建
        import faiss
        dim = self.embedding_dim
        # 使用 IndexFlatIP（内积），需要配合 L2 归一化实现余弦相似度
        index = faiss.IndexFlatIP(dim)
        self._collections[coll_name] = {
            "index": index,
            "docs": [],
            "metas": [],
        }
        return self._collections[coll_name]

    def _save_collection(self, coll_name: str, position_name: str = None):
        """将 collection 持久化到磁盘"""
        if coll_name not in self._collections:
            return
        coll = self._collections[coll_name]
        import faiss
        faiss.write_index(coll["index"], self._get_index_path(coll_name))
        data = {
            "position_name": position_name or coll_name,
            "docs": coll["docs"],
            "metas": coll["metas"],
        }
        with open(self._get_meta_path(coll_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    # ========== 公开 API ==========

    def add_documents(
        self,
        position_name: str,
        chunks: list[str],
        metadata: dict = None,
    ) -> int:
        """
        将文档块向量化并存入 FAISS 索引。
        返回存储的文档块数量。
        """
        if not self._available:
            raise RuntimeError("Vector store is not available")
        if not chunks:
            return 0

        coll_name = self._sanitize_collection_name(position_name)
        coll = self._load_collection(coll_name)

        # 向量化 + L2 归一化（配合 IndexFlatIP 实现余弦相似度）
        import faiss
        embeddings = self.embedding_model.encode(chunks).astype(np.float32)
        faiss.normalize_L2(embeddings)

        # 添加到 FAISS 索引
        coll["index"].add(embeddings)

        # 准备 metadata
        if metadata is None:
            metadata = {}
        for i, chunk in enumerate(chunks):
            meta = dict(metadata)
            if not meta:
                meta["source"] = "upload"
            meta["chunk_id"] = str(uuid.uuid4())
            coll["docs"].append(chunk)
            coll["metas"].append(meta)

        # 持久化
        self._save_collection(coll_name, position_name)

        logger.info(f"Added {len(chunks)} chunks to collection '{position_name}'")
        return len(chunks)

    def search(
        self,
        position_name: str,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """
        向量检索，返回最相关的文档块。
        返回格式：[{content, score, metadata}, ...]
        """
        if not self._available:
            return []

        coll_name = self._sanitize_collection_name(position_name)
        coll = self._load_collection(coll_name)

        total = coll["index"].ntotal
        if total == 0:
            return []

        # 查询向量化 + 归一化
        import faiss
        query_embedding = self.embedding_model.encode([query]).astype(np.float32)
        faiss.normalize_L2(query_embedding)

        k = min(top_k, total)
        distances, indices = coll["index"].search(query_embedding, k)

        output = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx < 0 or idx >= len(coll["docs"]):
                continue
            # IndexFlatIP 返回内积（余弦相似度），范围 [-1, 1]
            score = float(distances[0][i])
            output.append({
                "content": coll["docs"][idx],
                "score": round(score, 4),
                "metadata": coll["metas"][idx],
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        return output

    def delete_collection(self, position_name: str) -> bool:
        """删除指定岗位的向量知识库"""
        if not self._available:
            return False

        coll_name = self._sanitize_collection_name(position_name)
        index_path = self._get_index_path(coll_name)
        meta_path = self._get_meta_path(coll_name)

        deleted = False
        for path in (index_path, meta_path):
            if os.path.exists(path):
                os.remove(path)
                deleted = True

        if coll_name in self._collections:
            del self._collections[coll_name]

        if deleted:
            logger.info(f"Deleted collection: {coll_name}")
        return deleted

    def list_collections(self) -> list[dict]:
        """列出所有知识库及其文档数"""
        if not self._available:
            return []

        result = []
        try:
            for filename in os.listdir(self._index_dir):
                if filename.endswith(".json"):
                    coll_name = filename[:-5]  # 去掉 .json
                    if coll_name.startswith("kb_"):
                        meta_path = os.path.join(self._index_dir, filename)
                        try:
                            with open(meta_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            count = len(data.get("docs", []))
                            position_name = data.get("position_name", coll_name[3:])
                        except Exception:
                            count = 0
                            position_name = coll_name[3:]
                        result.append({
                            "position_name": position_name,
                            "document_count": count,
                        })
        except Exception as e:
            logger.warning(f"Failed to list collections: {e}")
        return result

    def get_collection_stats(self, position_name: str) -> Optional[dict]:
        """获取指定岗位知识库的统计信息"""
        if not self._available:
            return None

        coll_name = self._sanitize_collection_name(position_name)
        try:
            coll = self._load_collection(coll_name)
            return {
                "position_name": position_name,
                "document_count": coll["index"].ntotal,
            }
        except Exception:
            return None
