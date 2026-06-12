"""
SQLAlchemy ORM 模型 — 平台化数据库表结构

表关系概览：
  User 1─* InterviewSession
  User 1─* Position
  User 1─* Upload
  User *─* Team (多对多)
  Team 1─* Position
  InterviewSession 1─* ChatMessage
  InterviewSession 1─* QARecord
  InterviewSession 1─1 InterviewReport
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from database import Base


# ── 工具函数 ──

def _uuid_pk():
    """生成 UUID 主键（兼容 SQLite/PostgreSQL）"""
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _utc_now():
    """UTC 当前时间"""
    return datetime.now(timezone.utc)


# ========================================================================
# 用户与团队
# ========================================================================

# 用户←→团队 多对多关联表
team_members = Table(
    "team_members",
    Base.metadata,
    Column("team_id", String(36), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role", Enum("admin", "member", "viewer", name="team_member_role"), default="member"),
    Column("joined_at", DateTime, default=_utc_now),
)


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = _uuid_pk()
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False, default="用户")
    avatar_url = Column(String(500), nullable=True)
    role = Column(
        Enum("user", "admin", "enterprise", name="user_role"),
        default="user",
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    preferences = Column(JSON, default=dict, nullable=False)  # 用户偏好（模型、语言等）
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    sessions = relationship("InterviewSession", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="user", cascade="all, delete-orphan")
    teams = relationship("Team", secondary=team_members, back_populates="members")

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )


class Team(Base):
    """团队表"""
    __tablename__ = "teams"

    id = _uuid_pk()
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    max_members = Column(Integer, default=50)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("User", secondary=team_members, back_populates="teams")
    positions = relationship("Position", back_populates="team")
    templates = relationship("InterviewTemplate", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_teams_owner", "owner_id"),
    )


# ========================================================================
# 岗位
# ========================================================================

class JD(Base):
    """岗位 JD 表（一条记录 = 一份 JD 文档）"""
    __tablename__ = "jds"

    id = _uuid_pk()
    position_id = Column(String(36), ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # 关系
    position = relationship("Position", back_populates="jds")


class Position(Base):
    """岗位表"""
    __tablename__ = "positions"

    id = _uuid_pk()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    position_type = Column(String(20), default="未知")  # "技术岗" / "非技术岗" / "未知"
    is_public = Column(Boolean, default=False)  # 团队内是否公开
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    user = relationship("User", back_populates="positions")
    team = relationship("Team", back_populates="positions")
    jds = relationship("JD", back_populates="position", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_positions_user", "user_id"),
        Index("idx_positions_team", "team_id"),
        Index("idx_positions_name", "user_id", "name", unique=True),
    )


# ========================================================================
# 面试会话 + 消息 + 报告
# ========================================================================

class InterviewSession(Base):
    """面试会话表 — 一次完整的模拟面试"""
    __tablename__ = "interview_sessions"

    id = _uuid_pk()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(String(36), ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    mode = Column(
        Enum("interviewer", "candidate", name="interview_mode"),
        nullable=False,
    )
    candidate_level = Column(
        Enum("intern", "new_grad", "experienced", name="candidate_level"),
        nullable=True,
    )
    interview_round = Column(
        Enum("first", "second", "hr", name="interview_round"),
        nullable=True,
    )
    model_used = Column(String(100), nullable=True)       # 使用的 LLM 模型
    coding_enabled = Column(Boolean, default=False)        # 是否启用编程题
    duration_minutes = Column(Integer, default=30)         # 计划时长
    questions_planned = Column(Integer, default=0)         # 计划题数
    questions_answered = Column(Integer, default=0)        # 已答题数
    status = Column(
        Enum("active", "paused", "completed", "cancelled", name="session_status"),
        default="active",
    )
    plan_snapshot = Column(JSON, default=dict)             # 面试计划快照
    started_at = Column(DateTime, default=_utc_now, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    # 关系
    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")
    qa_records = relationship("QARecord", back_populates="session", cascade="all, delete-orphan",
                              order_by="QARecord.question_number")
    report = relationship("InterviewReport", back_populates="session", uselist=False,
                          cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_sessions_user", "user_id"),
        Index("idx_sessions_status", "user_id", "status"),
        Index("idx_sessions_date", "user_id", "started_at"),
    )


class ChatMessage(Base):
    """对话消息表"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("system", "user", "assistant", name="message_role"), nullable=False)
    content = Column(Text, nullable=False, default="")
    reasoning = Column(Text, nullable=True)               # 思考链内容
    token_count = Column(Integer, default=0)               # token 计数
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # 关系
    session = relationship("InterviewSession", back_populates="messages")

    __table_args__ = (
        Index("idx_messages_session", "session_id", "created_at"),
    )


class QARecord(Base):
    """问答记录表 — 结构化的问答对"""
    __tablename__ = "qa_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question = Column(Text, nullable=False)                # AI 面试官的提问
    answer = Column(Text, nullable=False, default="")      # 候选人的回答
    answer_chars = Column(Integer, default=0)              # 回答字数
    answer_duration_sec = Column(Float, default=0.0)       # 回答耗时（秒）
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # 关系
    session = relationship("InterviewSession", back_populates="qa_records")

    __table_args__ = (
        Index("idx_qa_session", "session_id", "question_number"),
    )


class InterviewReport(Base):
    """面试报告表"""
    __tablename__ = "interview_reports"

    id = _uuid_pk()
    session_id = Column(String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"),
                        nullable=False, unique=True)
    content = Column(Text, nullable=False, default="")     # Markdown 报告全文
    scores = Column(JSON, default=dict)                    # {"技术能力": 85, "沟通表达": 78, ...}
    dimensions = Column(JSON, default=list)                # [{"name":"算法","score":80,"comment":"..."}]
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # 关系
    session = relationship("InterviewSession", back_populates="report")


# ========================================================================
# 上传文件
# ========================================================================

class Upload(Base):
    """上传文件记录表"""
    __tablename__ = "uploads"

    id = _uuid_pk()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    type = Column(Enum("resume", "code", "project", name="upload_type"), nullable=False)
    text = Column(Text, nullable=False, default="")
    preview = Column(String(300), default="")
    file_count = Column(Integer, default=1)
    tech_stack = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # 关系
    user = relationship("User", back_populates="uploads")

    __table_args__ = (
        Index("idx_uploads_user", "user_id"),
        Index("idx_uploads_type", "user_id", "type"),
    )


# ========================================================================
# 面试模板
# ========================================================================

class InterviewTemplate(Base):
    """面试模板表 — 可复用的面试配置"""
    __tablename__ = "interview_templates"

    id = _uuid_pk()
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    mode = Column(Enum("interviewer", "candidate", name="template_mode"), nullable=False)
    candidate_level = Column(Enum("intern", "new_grad", "experienced", name="template_level"), nullable=True)
    interview_round = Column(Enum("first", "second", "hr", name="template_round"), nullable=True)
    duration_minutes = Column(Integer, default=30)
    coding_enabled = Column(Boolean, default=False)
    system_prompt_extra = Column(Text, default="")         # 附加到 system prompt 的说明
    question_tags = Column(JSON, default=list)             # 关联的题目标签
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    team = relationship("Team", back_populates="templates")
    creator = relationship("User", foreign_keys=[created_by])


# ========================================================================
# 自定义题库
# ========================================================================

class QuestionBankItem(Base):
    """自定义题库表（user_id 为空则为系统内置题目，全员可见）"""
    __tablename__ = "question_bank"

    id = _uuid_pk()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    team_id = Column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)                 # 题目完整内容
    category = Column(String(50), default="general")       # 分类：algorithm/frontend/backend/behavioral/...
    difficulty = Column(Enum("easy", "medium", "hard", name="question_difficulty"), default="medium")
    tags = Column(JSON, default=list)                      # 标签
    expected_answer = Column(Text, default="")             # 参考答案
    is_public = Column(Boolean, default=False)             # 是否公开到团队
    usage_count = Column(Integer, default=0)               # 被使用次数
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    user = relationship("User")

    __table_args__ = (
        Index("idx_qb_user", "user_id"),
        Index("idx_qb_team", "team_id"),
        Index("idx_qb_category", "category"),
        Index("idx_qb_difficulty", "difficulty"),
    )
