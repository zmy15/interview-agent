"""向量存储服务 — LangChain FAISS + HuggingFaceEmbeddings"""

import json
import logging
import os
import uuid
from typing import Optional

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
    """向量知识库管理器 — 基于 LangChain FAISS + HuggingFaceEmbeddings"""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._embeddings = None
        self._available = is_vector_store_available()
        self._index_dir = os.path.join(settings.CHROMA_PERSIST_PATH, "faiss_indexes")
        os.makedirs(self._index_dir, exist_ok=True)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def embeddings(self):
        """懒加载 HuggingFaceEmbeddings（LangChain 封装）"""
        if not self._available:
            raise RuntimeError("Vector store is not available: sentence-transformers/torch not installed")
        if self._embeddings is None:
            # 国内用户：设置 HuggingFace 镜像
            hf_endpoint = getattr(self._settings, "HF_ENDPOINT", "https://hf-mirror.com")
            hf_home = getattr(self._settings, "HF_HOME", None)
            if hf_endpoint:
                os.environ["HF_ENDPOINT"] = hf_endpoint
                logger.info(f"HF_ENDPOINT set to: {hf_endpoint}")
            if hf_home:
                os.environ["HF_HOME"] = hf_home
                os.makedirs(hf_home, exist_ok=True)

            from langchain_huggingface import HuggingFaceEmbeddings

            model_name = self._settings.EMBEDDING_MODEL
            logger.info(f"Loading embedding model via LangChain: {model_name}")

            # encode_kwargs normalize_embeddings=True → L2 归一化 → 余弦相似度
            self._embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    @property
    def embedding_dim(self) -> int:
        """获取嵌入向量维度"""
        test_vec = self.embeddings.embed_query("test")
        return len(test_vec)

    # ========== 存储路径（目录格式，LangChain FAISS 标准） ==========

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

    def _get_coll_dir(self, coll_name: str) -> str:
        """获取 collection 存储目录"""
        return os.path.join(self._index_dir, coll_name)

    def _collection_exists(self, coll_name: str) -> bool:
        """检查 LangChain FAISS collection 是否存在"""
        coll_dir = self._get_coll_dir(coll_name)
        return os.path.isdir(coll_dir) and os.path.exists(
            os.path.join(coll_dir, "index.faiss")
        )

    def _get_meta_path(self, coll_name: str) -> str:
        """获取 collection 元数据文件路径"""
        return os.path.join(self._get_coll_dir(coll_name), "collection_meta.json")

    def _save_collection_meta(self, coll_name: str, position_name: str):
        """保存 collection 元数据（含原始岗位名称，用于列表展示）"""
        meta_path = self._get_meta_path(coll_name)
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"position_name": position_name}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save collection meta for {coll_name}: {e}")

    def _load_collection_position_name(self, coll_name: str) -> str:
        """从元数据文件加载原始岗位名称，失败则返回 sanitized 名称"""
        meta_path = self._get_meta_path(coll_name)
        try:
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("position_name", coll_name[3:])
        except Exception:
            pass
        return coll_name[3:]  # 回退：去 kb_ 前缀

    # ========== 公开 API ==========

    def add_documents(
        self,
        position_name: str,
        chunks: list[str],
        metadata: dict = None,
    ) -> int:
        """
        将文档块向量化并存入 FAISS 索引。

        使用 LangChain FAISS wrapper，自动处理 L2 归一化和增量添加。

        Returns:
            存储的文档块数量
        """
        if not self._available:
            raise RuntimeError("Vector store is not available")
        if not chunks:
            return 0

        coll_name = self._sanitize_collection_name(position_name)
        coll_dir = self._get_coll_dir(coll_name)

        # 准备 metadata
        metadatas = []
        for i, chunk in enumerate(chunks):
            meta = dict(metadata) if metadata else {}
            if not meta:
                meta["source"] = "upload"
            meta["chunk_id"] = str(uuid.uuid4())
            metadatas.append(meta)

        from langchain_community.vectorstores import FAISS

        if self._collection_exists(coll_name):
            logger.info(f"Loading existing FAISS index for incremental add: {coll_name}")
            vectorstore = FAISS.load_local(
                coll_dir,
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
            vectorstore.add_texts(chunks, metadatas=metadatas)
        else:
            logger.info(f"Creating new FAISS index: {coll_name}")
            vectorstore = FAISS.from_texts(
                chunks,
                self.embeddings,
                metadatas=metadatas,
            )

        # 持久化到磁盘
        os.makedirs(coll_dir, exist_ok=True)
        vectorstore.save_local(coll_dir)

        # 额外保存 collection 元数据（含原始岗位名称）
        self._save_collection_meta(coll_name, position_name)

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
        score: 余弦相似度（0~1，越高越相关）
        """
        if not self._available:
            return []

        coll_name = self._sanitize_collection_name(position_name)
        coll_dir = self._get_coll_dir(coll_name)

        if not self._collection_exists(coll_name):
            return []

        from langchain_community.vectorstores import FAISS

        vectorstore = FAISS.load_local(
            coll_dir,
            self.embeddings,
            allow_dangerous_deserialization=True,
        )

        # similarity_search_with_score: normalize_embeddings=True 时，
        # FAISS 内部使用 IndexFlatIP，score 为余弦相似度
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=top_k)

        output = []
        for doc, score in docs_with_scores:
            output.append({
                "content": doc.page_content,
                "score": round(float(score), 4),
                "metadata": doc.metadata,
            })

        output.sort(key=lambda x: x["score"], reverse=True)
        return output

    def delete_collection(self, position_name: str) -> bool:
        """删除指定岗位的向量知识库（删除整个目录）"""
        if not self._available:
            return False

        coll_name = self._sanitize_collection_name(position_name)
        coll_dir = self._get_coll_dir(coll_name)

        if not os.path.isdir(coll_dir):
            return False

        import shutil
        try:
            shutil.rmtree(coll_dir)
            logger.info(f"Deleted collection: {coll_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {coll_name}: {e}")
            return False

    def list_collections(self) -> list[dict]:
        """列出所有知识库及其文档数"""
        if not self._available:
            return []

        result = []
        try:
            for entry in os.listdir(self._index_dir):
                coll_dir = os.path.join(self._index_dir, entry)
                if not os.path.isdir(coll_dir):
                    continue
                if not entry.startswith("kb_"):
                    continue

                # 从 LangChain FAISS 索引读取文档数
                index_path = os.path.join(coll_dir, "index.faiss")
                if os.path.exists(index_path):
                    import faiss
                    index = faiss.read_index(index_path)
                    count = index.ntotal
                else:
                    count = 0

                # 岗位名称：从元数据文件还原原始名称
                position_name = self._load_collection_position_name(entry)

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
        coll_dir = self._get_coll_dir(coll_name)

        if not self._collection_exists(coll_name):
            return None

        try:
            import faiss
            index = faiss.read_index(os.path.join(coll_dir, "index.faiss"))
            display_name = self._load_collection_position_name(coll_name)
            return {
                "position_name": display_name,
                "document_count": index.ntotal,
            }
        except Exception:
            return None
