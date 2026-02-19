#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库模块
提供本地文件和数据库的双存储支持
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, BigInteger, Index, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

Base = declarative_base()


# ==================== 环境变量支持 ====================

def load_db_config_from_env() -> dict:
    """
    从环境变量加载数据库配置
    支持的变量:
      DB_TYPE: 数据库类型 (sqlite/postgresql/mysql/external)
      DB_PATH: SQLite 数据库路径
      DB_HOST: 数据库主机地址
      DB_PORT: 数据库端口
      DB_NAME: 数据库名
      DB_USER: 数据库用户
      DB_PASS: 数据库密码
      DB_CONN_STR: 完整连接字符串 (用于外部数据库)
      DB_TABLE_PREFIX: 表前缀
    """
    config = {}

    db_type = os.environ.get('DB_TYPE', '').lower()
    if db_type:
        config['type'] = db_type

    # SQLite
    db_path = os.environ.get('DB_PATH', '')
    if db_path:
        config['sqlite'] = {'path': db_path}

    # PostgreSQL / MySQL 通用
    db_host = os.environ.get('DB_HOST', '')
    if db_host:
        if 'postgresql' in db_type:
            config['postgresql'] = {
                'host': db_host,
                'port': int(os.environ.get('DB_PORT', 5432)),
                'database': os.environ.get('DB_NAME', 'hyc'),
                'user': os.environ.get('DB_USER', 'postgres'),
                'password': os.environ.get('DB_PASS', '')
            }
        elif 'mysql' in db_type:
            config['mysql'] = {
                'host': db_host,
                'port': int(os.environ.get('DB_PORT', 3306)),
                'database': os.environ.get('DB_NAME', 'hyc'),
                'user': os.environ.get('DB_USER', 'root'),
                'password': os.environ.get('DB_PASS', '')
            }

    # 外部数据库连接字符串
    db_conn_str = os.environ.get('DB_CONN_STR', '')
    if db_conn_str:
        config['external'] = {'connection_string': db_conn_str}

    # 表前缀
    table_prefix = os.environ.get('DB_TABLE_PREFIX', '')
    if table_prefix:
        # 添加到对应类型的配置
        for db_key in ['sqlite', 'postgresql', 'mysql', 'external']:
            if db_key in config:
                config[db_key]['table_prefix'] = table_prefix

    return config


def merge_config(file_config: dict, env_config: dict) -> dict:
    """合并配置文件和环境变量配置"""
    merged = file_config.copy()

    # 如果有环境变量配置，合并 database 部分
    if 'database' in env_config and env_config['database']:
        if 'database' not in merged:
            merged['database'] = {}
        merged['database'].update(env_config['database'])

    return merged


# ==================== 数据库模型定义 ====================

# 表名前缀（可在初始化时设置）
_TABLE_PREFIX = ''
_SCHEMA_VERSION = 1  # 当前Schema版本


def set_table_prefix(prefix: str):
    """设置表前缀"""
    global _TABLE_PREFIX
    _TABLE_PREFIX = prefix


def get_table_name(base_name: str) -> str:
    """获取带前缀的表名"""
    return f"{_TABLE_PREFIX}{base_name}"


class SchemaVersion(Base):
    """数据库结构版本表"""
    __tablename__ = 'schema_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, unique=True)
    applied_at = Column(Float, default=time.time)
    description = Column(String(255), nullable=True)


class FileRecord(Base):
    """文件记录表"""
    __tablename__ = 'files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(64), unique=True, nullable=False, index=True)  # 文件唯一ID
    path = Column(String(1024), nullable=False, index=True)  # 文件路径
    name = Column(String(512), nullable=False)  # 文件名
    size = Column(BigInteger, default=0)  # 文件大小
    hash = Column(String(64), nullable=True)  # 文件hash
    mime_type = Column(String(128), nullable=True)  # MIME类型
    is_dir = Column(Boolean, default=False)  # 是否是目录
    created_at = Column(Float, default=time.time)  # 创建时间
    updated_at = Column(Float, default=time.time)  # 更新时间
    last_accessed = Column(Float, default=time.time)  # 最后访问时间
    download_count = Column(Integer, default=0)  # 下载次数
    is_deleted = Column(Boolean, default=False, index=True)  # 软删除标记
    sync_status = Column(String(32), default='synced')  # 同步状态: pending, synced, error

    __table_args__ = (
        Index('idx_files_path_status', 'path', 'is_deleted'),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'file_id': self.file_id,
            'path': self.path,
            'name': self.name,
            'size': self.size,
            'hash': self.hash,
            'mime_type': self.mime_type,
            'is_dir': self.is_dir,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_accessed': self.last_accessed,
            'download_count': self.download_count,
            'is_deleted': self.is_deleted,
            'sync_status': self.sync_status
        }


class SyncRecord(Base):
    """同步记录表"""
    __tablename__ = 'sync_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_id = Column(String(64), unique=True, nullable=False, index=True)
    source_type = Column(String(64), nullable=False)  # 同步源类型
    source_name = Column(String(256), nullable=False)  # 同步源名称
    status = Column(String(32), default='pending')  # pending, running, completed, failed
    total_files = Column(Integer, default=0)
    synced_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    total_size = Column(BigInteger, default=0)
    synced_size = Column(BigInteger, default=0)
    started_at = Column(Float, default=time.time)
    completed_at = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'sync_id': self.sync_id,
            'source_type': self.source_type,
            'source_name': self.source_name,
            'status': self.status,
            'total_files': self.total_files,
            'synced_files': self.synced_files,
            'failed_files': self.failed_files,
            'total_size': self.total_size,
            'synced_size': self.synced_size,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'error_message': self.error_message
        }


class CacheRecord(Base):
    """缓存记录表"""
    __tablename__ = 'cache_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(512), unique=True, nullable=False, index=True)
    cache_type = Column(String(64), nullable=False)  # docker, apt, pypi, etc.
    file_path = Column(String(1024), nullable=True)
    file_size = Column(BigInteger, default=0)
    file_hash = Column(String(64), nullable=True)
    hits = Column(Integer, default=0)
    created_at = Column(Float, default=time.time)
    expires_at = Column(Float, nullable=True)
    last_hit = Column(Float, default=time.time)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'cache_key': self.cache_key,
            'cache_type': self.cache_type,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'hits': self.hits,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'last_hit': self.last_hit
        }


class DownloadRecord(Base):
    """下载记录表"""
    __tablename__ = 'download_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String(1024), nullable=False, index=True)
    file_size = Column(BigInteger, default=0)
    download_time = Column(Float, default=time.time)
    duration = Column(Float, default=0)
    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'download_time': self.download_time,
            'duration': self.duration,
            'client_ip': self.client_ip,
            'user_agent': self.user_agent,
            'success': self.success,
            'error_message': self.error_message
        }


class MonitorHistoryRecord(Base):
    """监控历史记录表"""
    __tablename__ = 'monitor_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Float, nullable=False, index=True)
    cpu_percent = Column(Float, default=0)
    memory_percent = Column(Float, default=0)
    disk_percent = Column(Float, default=0)
    network_rx = Column(BigInteger, default=0)
    network_tx = Column(BigInteger, default=0)
    active_connections = Column(Integer, default=0)
    server_uptime = Column(Float, default=0)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'disk_percent': self.disk_percent,
            'network_rx': self.network_rx,
            'network_tx': self.network_tx,
            'active_connections': self.active_connections,
            'server_uptime': self.server_uptime
        }


class WebhookRecord(Base):
    """Webhook配置记录表"""
    __tablename__ = 'webhooks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    events = Column(Text, nullable=True)  # JSON 格式存储
    secret = Column(String(255), nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)

    def to_dict(self) -> dict:
        import json
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'events': json.loads(self.events) if self.events else [],
            'secret': self.secret,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class WebhookDeliveryRecord(Base):
    """Webhook交付记录表"""
    __tablename__ = 'webhook_deliveries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    webhook_id = Column(Integer, nullable=False, index=True)
    event = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)  # success, failed, pending
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(Float, default=time.time, index=True)
    retry_count = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'webhook_id': self.webhook_id,
            'event': self.event,
            'status': self.status,
            'status_code': self.status_code,
            'response_body': self.response_body[:500] if self.response_body else None,
            'error_message': self.error_message,
            'duration_ms': self.duration_ms,
            'created_at': self.created_at,
            'retry_count': self.retry_count
        }


class UserRecord(Base):
    """用户账号记录表"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)  # bcrypt 加密后的哈希
    role = Column(String(50), default='admin')  # admin, user
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    last_login = Column(Float, nullable=True)
    login_count = Column(Integer, default=0)
    failed_attempts = Column(Integer, default=0)  # 登录失败次数
    locked_until = Column(Float, nullable=True)  # 锁定直到时间戳
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    enabled = Column(Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'password_hash': self.password_hash,
            'role': self.role,
            'email': self.email,
            'phone': self.phone,
            'last_login': self.last_login,
            'login_count': self.login_count,
            'failed_attempts': self.failed_attempts,
            'locked_until': self.locked_until,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'enabled': self.enabled
        }


class LoginLogRecord(Base):
    """登录日志记录表"""
    __tablename__ = 'login_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False)  # success, failed, locked
    reason = Column(String(255), nullable=True)
    created_at = Column(Float, default=time.time, index=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'status': self.status,
            'reason': self.reason,
            'created_at': self.created_at
        }


# ==================== 数据库管理器 ====================

class DatabaseManager:
    """数据库管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config: dict = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: dict = None):
        if self._initialized:
            return

        self.config = config or {}
        self.db_type = self.config.get('type', 'sqlite')  # sqlite, postgresql, mysql, external

        # 获取数据库配置
        db_config = self.config.get(self.db_type, {})

        # 获取表前缀（支持多租户）
        self.table_prefix = db_config.get('table_prefix', '')

        # 创建数据库引擎
        self._create_engine(db_config)

        # 设置表前缀（需要在创建表之前）
        if self.table_prefix:
            set_table_prefix(self.table_prefix)

        # 自动创建表结构
        self._create_tables()

        # 会话工厂
        self.Session = sessionmaker(bind=self.engine)

        self._initialized = True
        self._operation_count = 0
        self._last_sync_time = time.time()
        self._sync_interval = self.config.get('sync_interval', 60)  # 默认60秒同步

    def _create_tables(self):
        """自动创建数据库表结构"""
        try:
            # 尝试创建所有表
            Base.metadata.create_all(self.engine)
            # 对于 MySQL，需要提交事务
            if self.db_type == 'mysql':
                from sqlalchemy import text
                with self.engine.connect() as conn:
                    conn.commit()
        except Exception as e:
            print(f"警告: 创建表结构失败: {e}")
            print("将尝试创建数据库...")
            self._create_database()

    def _create_database(self):
        """创建数据库（如果不存在）"""
        # SQLite 不需要预创建数据库
        if self.db_type == 'sqlite':
            return

        # 对于 PostgreSQL/MySQL，尝试创建数据库
        try:
            if self.db_type == 'postgresql':
                # 连接到默认数据库 postgres
                from sqlalchemy import text
                db_config = self.config.get('postgresql', {})
                host = db_config.get('host', 'localhost')
                port = db_config.get('port', 5432)
                user = db_config.get('user', 'postgres')
                password = db_config.get('password', '')
                database = db_config.get('database', 'hyc')

                temp_engine = create_engine(
                    f"postgresql://{user}:{password}@{host}:{port}/postgres"
                )
                with temp_engine.connect() as conn:
                    # 检查数据库是否存在
                    result = conn.execute(
                        text(f"SELECT 1 FROM pg_database WHERE datname = '{database}'")
                    ).fetchone()
                    if not result:
                        conn.execute(text(f"CREATE DATABASE {database}"))
                        print(f"已创建数据库: {database}")
                temp_engine.dispose()

            elif self.db_type == 'mysql':
                from sqlalchemy import text
                db_config = self.config.get('mysql', {})
                host = db_config.get('host', 'localhost')
                port = db_config.get('port', 3306)
                user = db_config.get('user', 'root')
                password = db_config.get('password', '')

                temp_engine = create_engine(
                    f"mysql+pymysql://{user}:{password}@{host}:{port}"
                )
                with temp_engine.connect() as conn:
                    db_config = self.config.get('mysql', {})
                    database = db_config.get('database', 'hyc')
                    try:
                        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4"))
                        conn.commit()  # 提交事务
                        print(f"已创建/确认数据库: {database}")
                    except Exception as e:
                        print(f"警告: 创建数据库失败: {e}")
                temp_engine.dispose()

        except Exception as e:
            print(f"警告: 创建数据库失败: {e}")

    def _create_engine(self, db_config: dict):
        """创建数据库引擎"""
        if self.db_type == 'sqlite':
            # SQLite 配置
            db_path = db_config.get('path', './data/hyc.db')
            # 确保数据库目录存在
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            db_url = f"sqlite:///{db_path}"
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600
            )

        elif self.db_type == 'postgresql':
            # PostgreSQL 配置
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 5432)
            database = db_config.get('database', 'hyc')
            user = db_config.get('user', 'postgres')
            password = db_config.get('password', '')
            ssl_mode = db_config.get('ssl_mode', 'prefer')
            timeout = db_config.get('connection_timeout', 30)

            db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=db_config.get('pool_size', 5),
                max_overflow=db_config.get('max_overflow', 10),
                pool_recycle=3600,
                connect_args={'connect_timeout': timeout}
            )

        elif self.db_type == 'mysql':
            # MySQL 配置
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 3306)
            database = db_config.get('database', 'hyc')
            user = db_config.get('user', 'root')
            password = db_config.get('password', '')
            charset = db_config.get('charset', 'utf8mb4')
            timeout = db_config.get('connection_timeout', 30)

            db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=db_config.get('pool_size', 5),
                max_overflow=db_config.get('max_overflow', 10),
                pool_recycle=3600,
                connect_args={'connect_timeout': timeout}
            )

        elif self.db_type == 'external':
            # 外部数据库 - 使用完整连接字符串
            connection_string = db_config.get('connection_string', '')
            if not connection_string:
                raise ValueError("外部数据库配置需要提供 connection_string")

            self.engine = create_engine(
                connection_string,
                poolclass=QueuePool,
                pool_size=db_config.get('pool_size', 5),
                max_overflow=db_config.get('max_overflow', 10),
                pool_recycle=3600
            )

        else:
            raise ValueError(f"不支持的数据库类型: {self.db_type}. 支持: sqlite, postgresql, mysql, external")

    @contextmanager
    def session(self):
        """获取数据库会话"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== 文件操作 ====================

    def add_file(self, file_id: str, path: str, name: str,
                 size: int = 0, hash: str = None, mime_type: str = None,
                 is_dir: bool = False, created_at: float = None) -> FileRecord:
        """添加文件记录"""
        with self.session() as session:
            record = FileRecord(
                file_id=file_id,
                path=path,
                name=name,
                size=size,
                hash=hash,
                mime_type=mime_type,
                is_dir=is_dir,
                created_at=created_at or time.time(),
                updated_at=time.time(),
                sync_status='pending'
            )
            session.add(record)
            self._operation_count += 1
            return record

    def update_file(self, file_id: str, **kwargs) -> Optional[FileRecord]:
        """更新文件记录"""
        with self.session() as session:
            record = session.query(FileRecord).filter(
                FileRecord.file_id == file_id,
                FileRecord.is_deleted == False
            ).first()
            if record:
                for key, value in kwargs.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                record.updated_at = time.time()
                record.sync_status = 'pending'
                self._operation_count += 1
            return record

    def delete_file(self, file_id: str, hard: bool = False) -> bool:
        """删除文件记录"""
        with self.session() as session:
            record = session.query(FileRecord).filter(
                FileRecord.file_id == file_id
            ).first()
            if record:
                if hard:
                    session.delete(record)
                else:
                    record.is_deleted = True
                    record.updated_at = time.time()
                    record.sync_status = 'pending'
                self._operation_count += 1
                return True
            return False

    def get_file(self, file_id: str) -> Optional[FileRecord]:
        """获取文件记录"""
        with self.session() as session:
            return session.query(FileRecord).filter(
                FileRecord.file_id == file_id,
                FileRecord.is_deleted == False
            ).first()

    def get_file_by_path(self, path: str) -> Optional[FileRecord]:
        """根据路径获取文件记录"""
        with self.session() as session:
            return session.query(FileRecord).filter(
                FileRecord.path == path,
                FileRecord.is_deleted == False
            ).first()

    def list_files(self, path: str = '/', recursive: bool = False,
                   include_deleted: bool = False, limit: int = 1000,
                   offset: int = 0) -> List[FileRecord]:
        """列出文件记录"""
        with self.session() as session:
            query = session.query(FileRecord)

            if not include_deleted:
                query = query.filter(FileRecord.is_deleted == False)

            if path and path != '/':
                if recursive:
                    query = query.filter(FileRecord.path.startswith(path))
                else:
                    parent_path = path.rstrip('/') + '/'
                    query = query.filter(
                        (FileRecord.path == path) |
                        (FileRecord.path.startswith(parent_path))
                    )

            return query.order_by(FileRecord.path).offset(offset).limit(limit).all()

    def search_files(self, keyword: str, limit: int = 100) -> List[FileRecord]:
        """搜索文件"""
        with self.session() as session:
            return session.query(FileRecord).filter(
                FileRecord.is_deleted == False,
                (FileRecord.name.contains(keyword) |
                 FileRecord.path.contains(keyword))
            ).limit(limit).all()

    def increment_download_count(self, file_id: str) -> bool:
        """增加下载计数（通过 file_id 查找）"""
        with self.session() as session:
            record = session.query(FileRecord).filter(
                FileRecord.file_id == file_id
            ).first()
            if record:
                record.download_count += 1
                self._operation_count += 1
                return True
            return False

    # ==================== 同步记录操作 ====================

    def add_sync_record(self, sync_id: str, source_type: str,
                        source_name: str, **kwargs) -> SyncRecord:
        """添加同步记录"""
        with self.session() as session:
            record = SyncRecord(
                sync_id=sync_id,
                source_type=source_type,
                source_name=source_name,
                started_at=time.time(),
                **kwargs
            )
            session.add(record)
            return record

    def update_sync_record(self, sync_id: str, **kwargs) -> Optional[SyncRecord]:
        """更新同步记录"""
        with self.session() as session:
            record = session.query(SyncRecord).filter(
                SyncRecord.sync_id == sync_id
            ).first()
            if record:
                for key, value in kwargs.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                return record
            return None

    def get_sync_records(self, limit: int = 50) -> List[SyncRecord]:
        """获取同步记录"""
        with self.session() as session:
            return session.query(SyncRecord).order_by(
                SyncRecord.started_at.desc()
            ).limit(limit).all()

    # ==================== 缓存记录操作 ====================

    def add_cache_record(self, cache_key: str, cache_type: str,
                         **kwargs) -> CacheRecord:
        """添加缓存记录"""
        with self.session() as session:
            record = CacheRecord(
                cache_key=cache_key,
                cache_type=cache_type,
                **kwargs
            )
            session.add(record)
            return record

    def update_cache_record(self, cache_key: str, **kwargs) -> Optional[CacheRecord]:
        """更新缓存记录"""
        with self.session() as session:
            record = session.query(CacheRecord).filter(
                CacheRecord.cache_key == cache_key
            ).first()
            if record:
                for key, value in kwargs.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                return record
            return None

    def get_cache_record(self, cache_key: str) -> Optional[CacheRecord]:
        """获取缓存记录"""
        with self.session() as session:
            return session.query(CacheRecord).filter(
                CacheRecord.cache_key == cache_key
            ).first()

    def increment_cache_hits(self, cache_key: str) -> bool:
        """增加缓存命中次数"""
        with self.session() as session:
            record = session.query(CacheRecord).filter(
                CacheRecord.cache_key == cache_key
            ).first()
            if record:
                record.hits += 1
                record.last_hit = time.time()
                return True
            return False

    def list_cache_records(self, cache_type: str = None,
                           limit: int = 100) -> List[CacheRecord]:
        """列出缓存记录"""
        with self.session() as session:
            query = session.query(CacheRecord)
            if cache_type:
                query = query.filter(CacheRecord.cache_type == cache_type)
            return query.order_by(CacheRecord.hits.desc()).limit(limit).all()

    # ==================== 下载记录操作 ====================

    def add_download_record(self, file_path: str, file_size: int = 0,
                           client_ip: str = None, user_agent: str = None,
                           success: bool = True, error_message: str = None,
                           duration: float = 0) -> DownloadRecord:
        """添加下载记录"""
        with self.session() as session:
            record = DownloadRecord(
                file_path=file_path,
                file_size=file_size,
                download_time=time.time(),
                client_ip=client_ip,
                user_agent=user_agent,
                success=success,
                error_message=error_message,
                duration=duration
            )
            session.add(record)
            self._operation_count += 1
            return record

    def get_download_records(self, file_path: str = None,
                             limit: int = 100) -> List[DownloadRecord]:
        """获取下载记录"""
        with self.session() as session:
            query = session.query(DownloadRecord)
            if file_path:
                query = query.filter(DownloadRecord.file_path == file_path)
            return query.order_by(
                DownloadRecord.download_time.desc()
            ).limit(limit).all()

    def get_download_stats(self, days: int = 7) -> dict:
        """获取下载统计"""
        from sqlalchemy import func
        start_time = time.time() - (days * 86400)

        with self.session() as session:
            total_downloads = session.query(func.count(DownloadRecord.id)).filter(
                DownloadRecord.download_time >= start_time
            ).scalar()

            successful_downloads = session.query(func.count(DownloadRecord.id)).filter(
                DownloadRecord.download_time >= start_time,
                DownloadRecord.success == True
            ).scalar()

            total_bytes = session.query(func.sum(DownloadRecord.file_size)).filter(
                DownloadRecord.download_time >= start_time,
                DownloadRecord.success == True
            ).scalar() or 0

            return {
                'total_downloads': total_downloads,
                'successful_downloads': successful_downloads,
                'failed_downloads': total_downloads - successful_downloads,
                'total_bytes': total_bytes,
                'total_human': self._format_size(total_bytes)
            }

    # ==================== 监控历史记录 ====================

    def add_monitor_record(self, cpu_percent: float = 0, memory_percent: float = 0,
                           disk_percent: float = 0, network_rx: int = 0,
                           network_tx: int = 0, active_connections: int = 0,
                           server_uptime: float = 0) -> Optional[MonitorHistoryRecord]:
        """添加监控记录"""
        with self.session() as session:
            record = MonitorHistoryRecord(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                network_rx=network_rx,
                network_tx=network_tx,
                active_connections=active_connections,
                server_uptime=server_uptime
            )
            session.add(record)
            self._operation_count += 1
            return record

    def get_monitor_history(self, hours: int = 24) -> List[MonitorHistoryRecord]:
        """获取监控历史记录"""
        from sqlalchemy import func
        cutoff_time = time.time() - (hours * 3600)

        with self.session() as session:
            # 按时间聚合，每5分钟一个数据点
            records = session.query(
                MonitorHistoryRecord
            ).filter(
                MonitorHistoryRecord.timestamp >= cutoff_time
            ).order_by(
                MonitorHistoryRecord.timestamp.desc()
            ).all()

            return records

    def get_monitor_stats(self, hours: int = 24) -> dict:
        """获取监控统计数据"""
        from sqlalchemy import func
        cutoff_time = time.time() - (hours * 3600)

        with self.session() as session:
            stats = session.query(
                func.avg(MonitorHistoryRecord.cpu_percent).label('avg_cpu'),
                func.max(MonitorHistoryRecord.cpu_percent).label('max_cpu'),
                func.avg(MonitorHistoryRecord.memory_percent).label('avg_memory'),
                func.max(MonitorHistoryRecord.memory_percent).label('max_memory'),
                func.avg(MonitorHistoryRecord.disk_percent).label('avg_disk'),
                func.max(MonitorHistoryRecord.disk_percent).label('max_disk'),
                func.sum(MonitorHistoryRecord.network_rx).label('total_rx'),
                func.sum(MonitorHistoryRecord.network_tx).label('total_tx')
            ).filter(
                MonitorHistoryRecord.timestamp >= cutoff_time
            ).first()

            return {
                'avg_cpu': round(stats.avg_cpu, 1) if stats.avg_cpu else 0,
                'max_cpu': round(stats.max_cpu, 1) if stats.max_cpu else 0,
                'avg_memory': round(stats.avg_memory, 1) if stats.avg_memory else 0,
                'max_memory': round(stats.max_memory, 1) if stats.max_memory else 0,
                'avg_disk': round(stats.avg_disk, 1) if stats.avg_disk else 0,
                'max_disk': round(stats.max_disk, 1) if stats.max_disk else 0,
                'total_rx': stats.total_rx or 0,
                'total_tx': stats.total_tx or 0
            }

    # ==================== Webhook 管理 ====================

    def get_webhooks(self) -> List[WebhookRecord]:
        """获取所有 webhook 配置"""
        import json
        with self.session() as session:
            return session.query(WebhookRecord).order_by(
                WebhookRecord.created_at.desc()
            ).all()

    def get_webhook(self, webhook_id: int) -> Optional[WebhookRecord]:
        """获取单个 webhook 配置"""
        with self.session() as session:
            return session.query(WebhookRecord).filter(
                WebhookRecord.id == webhook_id
            ).first()

    def add_webhook(self, name: str, url: str, events: List[str] = None,
                   secret: str = None, enabled: bool = True) -> WebhookRecord:
        """添加 webhook 配置"""
        import json
        with self.session() as session:
            record = WebhookRecord(
                name=name,
                url=url,
                events=json.dumps(events or []),
                secret=secret,
                enabled=enabled,
                created_at=time.time(),
                updated_at=time.time()
            )
            session.add(record)
            return record

    def update_webhook(self, webhook_id: int, **kwargs) -> Optional[WebhookRecord]:
        """更新 webhook 配置"""
        import json
        with self.session() as session:
            record = session.query(WebhookRecord).filter(
                WebhookRecord.id == webhook_id
            ).first()
            if not record:
                return None

            if 'name' in kwargs:
                record.name = kwargs['name']
            if 'url' in kwargs:
                record.url = kwargs['url']
            if 'events' in kwargs:
                record.events = json.dumps(kwargs['events'])
            if 'secret' in kwargs:
                record.secret = kwargs['secret']
            if 'enabled' in kwargs:
                record.enabled = kwargs['enabled']

            record.updated_at = time.time()
            return record

    def delete_webhook(self, webhook_id: int) -> bool:
        """删除 webhook 配置"""
        with self.session() as session:
            result = session.query(WebhookRecord).filter(
                WebhookRecord.id == webhook_id
            ).delete()
            return result > 0

    # ==================== Webhook 交付记录 ====================

    def add_webhook_delivery(
        self,
        webhook_id: int,
        event: str,
        status: str,
        status_code: int = None,
        response_body: str = None,
        error_message: str = None,
        duration_ms: float = None,
        retry_count: int = 0
    ) -> WebhookDeliveryRecord:
        """添加 webhook 交付记录"""
        with self.session() as session:
            record = WebhookDeliveryRecord(
                webhook_id=webhook_id,
                event=event,
                status=status,
                status_code=status_code,
                response_body=response_body,
                error_message=error_message,
                duration_ms=duration_ms,
                created_at=time.time(),
                retry_count=retry_count
            )
            session.add(record)
            session.commit()
            return record

    def get_webhook_deliveries(
        self,
        webhook_id: int = None,
        status: str = None,
        limit: int = 50
    ) -> List[WebhookDeliveryRecord]:
        """获取 webhook 交付记录"""
        with self.session() as session:
            query = session.query(WebhookDeliveryRecord)

            if webhook_id:
                query = query.filter(WebhookDeliveryRecord.webhook_id == webhook_id)
            if status:
                query = query.filter(WebhookDeliveryRecord.status == status)

            return query.order_by(
                WebhookDeliveryRecord.created_at.desc()
            ).limit(limit).all()

    def get_webhook_stats(self, webhook_id: int = None) -> Dict:
        """获取 webhook 交付统计"""
        with self.session() as session:
            query = session.query(WebhookDeliveryRecord)
            if webhook_id:
                query = query.filter(WebhookDeliveryRecord.webhook_id == webhook_id)

            deliveries = query.all()

            total = len(deliveries)
            success = sum(1 for d in deliveries if d.status == 'success')
            failed = sum(1 for d in deliveries if d.status == 'failed')

            avg_duration = 0
            if deliveries:
                durations = [d.duration_ms for d in deliveries if d.duration_ms]
                if durations:
                    avg_duration = sum(durations) / len(durations)

            return {
                'total_deliveries': total,
                'success': success,
                'failed': failed,
                'pending': sum(1 for d in deliveries if d.status == 'pending'),
                'success_rate': (success / total * 100) if total > 0 else 0,
                'avg_duration_ms': round(avg_duration, 2)
            }

    def cleanup_webhook_deliveries(self, older_than: int = 604800) -> int:
        """
        清理旧的 webhook 交付记录

        Args:
            older_than: 清理多少秒之前的记录，默认 7 天 (604800 秒)

        Returns:
            删除的记录数量
        """
        with self.session() as session:
            cutoff = time.time() - older_than
            result = session.query(WebhookDeliveryRecord).filter(
                WebhookDeliveryRecord.created_at < cutoff
            ).delete()
            session.commit()
            return result

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    # ==================== 统计和同步 ====================

    def get_stats(self) -> dict:
        """获取数据库统计"""
        with self.session() as session:
            return {
                'total_files': session.query(FileRecord).filter(
                    FileRecord.is_deleted == False
                ).count(),
                'deleted_files': session.query(FileRecord).filter(
                    FileRecord.is_deleted == True
                ).count(),
                'total_sync_records': session.query(SyncRecord).count(),
                'total_cache_records': session.query(CacheRecord).count(),
                'total_download_records': session.query(DownloadRecord).count(),
                'pending_operations': self._operation_count
            }

    def get_download_stats(self, limit: int = 10000) -> dict:
        """获取下载统计数据（返回字典，避免会话关闭后访问对象问题）"""
        with self.session() as session:
            stats = {}
            # 直接查询需要的字段，在会话关闭前提取数据
            results = session.query(FileRecord.path, FileRecord.download_count).filter(
                FileRecord.is_deleted == False,
                FileRecord.download_count > 0
            ).limit(limit).all()
            for path, count in results:
                stats[path] = count
            return stats

    def get_pending_operations(self) -> int:
        """获取待同步操作数"""
        return self._operation_count

    def reset_pending_count(self):
        """重置待同步计数"""
        self._operation_count = 0
        self._last_sync_time = time.time()

    def cleanup_expired_cache(self) -> int:
        """清理过期缓存记录"""
        with self.session() as session:
            expired = session.query(CacheRecord).filter(
                CacheRecord.expires_at != None,
                CacheRecord.expires_at < time.time()
            ).delete()
            return expired

    # ==================== 用户管理 ====================

    def create_user(self, username: str, password_hash: str, role: str = 'admin', email: str = None) -> dict:
        """创建用户"""
        with self.session() as session:
            # 检查用户名是否已存在
            existing = session.query(UserRecord).filter_by(username=username).first()
            if existing:
                return {'success': False, 'error': '用户名已存在'}

            user = UserRecord(
                username=username,
                password_hash=password_hash,
                role=role,
                email=email,
                enabled=True
            )
            session.add(user)
            session.commit()
            return {'success': True, 'user_id': user.id}

    def get_user(self, username: str) -> dict:
        """获取用户信息"""
        with self.session() as session:
            user = session.query(UserRecord).filter_by(username=username).first()
            if user:
                return user.to_dict()
            return None

    def get_user_by_id(self, user_id: int) -> dict:
        """通过ID获取用户信息"""
        with self.session() as session:
            user = session.query(UserRecord).filter_by(id=user_id).first()
            if user:
                return user.to_dict()
            return None

    def update_password(self, username: str, new_password_hash: str) -> bool:
        """更新用户密码"""
        with self.session() as session:
            user = session.query(UserRecord).filter_by(username=username).first()
            if user:
                user.password_hash = new_password_hash
                user.updated_at = time.time()
                session.commit()
                return True
            return False

    def verify_user(self, username: str, password_hash: str) -> dict:
        """验证用户登录"""
        with self.session() as session:
            user = session.query(UserRecord).filter_by(username=username).first()

            if not user:
                return {'valid': False, 'reason': '用户不存在'}

            # 检查是否被锁定
            if user.locked_until and user.locked_until > time.time():
                return {'valid': False, 'reason': '账号已被锁定', 'locked_until': user.locked_until}

            # 检查是否启用
            if not user.enabled:
                return {'valid': False, 'reason': '账号已被禁用'}

            # 验证密码
            if user.password_hash == password_hash:
                # 登录成功
                user.last_login = time.time()
                user.login_count = (user.login_count or 0) + 1
                user.failed_attempts = 0
                user.locked_until = None
                session.commit()
                return {'valid': True, 'user': user.to_dict()}
            else:
                # 登录失败
                user.failed_attempts = (user.failed_attempts or 0) + 1

                # 连续失败5次锁定10分钟
                if user.failed_attempts >= 5:
                    user.locked_until = time.time() + 600  # 10分钟
                    session.commit()
                    return {'valid': False, 'reason': '密码错误次数过多，账号已锁定10分钟'}

                session.commit()
                return {'valid': False, 'reason': '用户名或密码错误'}

    def add_login_log(self, username: str, ip_address: str, status: str, reason: str = None, user_agent: str = None):
        """添加登录日志"""
        with self.session() as session:
            log = LoginLogRecord(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                status=status,
                reason=reason
            )
            session.add(log)
            session.commit()

    def get_login_logs(self, limit: int = 100, username: str = None) -> list:
        """获取登录日志"""
        with self.session() as session:
            query = session.query(LoginLogRecord).order_by(LoginLogRecord.created_at.desc())
            if username:
                query = query.filter(LoginLogRecord.username == username)
            logs = query.limit(limit).all()
            return [log.to_dict() for log in logs]

    def init_default_user(self, username: str, password: str):
        """初始化默认用户（如果不存在）"""
        # 使用 bcrypt 加密密码
        password_hash = self.hash_password(password)

        user = self.get_user(username)
        if not user:
            self.create_user(username, password_hash, 'admin')
            print(f"[数据库] 已创建默认用户: {username}")

    def hash_password(self, password: str) -> str:
        """使用 bcrypt 加密密码"""
        try:
            import bcrypt
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        except ImportError:
            # 如果 bcrypt 不可用，回退到 SHA256
            import hashlib
            salt = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
            return hashlib.sha256((password + salt).encode()).hexdigest()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码是否正确"""
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except ImportError:
            # 如果 bcrypt 不可用，回退到 SHA256 验证
            import hashlib
            # 尝试直接比较（可能是旧格式）
            if password_hash == password:
                return True
            # 尝试带 salt 验证
            for salt_len in range(1, 17):
                salt = password_hash[:salt_len] if len(password_hash) > salt_len else ""
                if len(salt) >= 4:
                    test_hash = hashlib.sha256((password + salt).encode()).hexdigest()
                    if test_hash == password_hash:
                        return True
            return False

    # ==================== 数据库迁移和健康检查 ====================

    def check_schema_version(self) -> bool:
        """检查并更新数据库结构版本"""
        try:
            # 确保所有表都存在（包括新增的表）
            Base.metadata.create_all(self.engine)

            with self.session() as session:
                # 检查版本表是否存在
                from sqlalchemy import inspect
                inspector = inspect(self.engine)
                tables = inspector.get_table_names()

                if 'schema_versions' not in tables:
                    # 首次运行，创建版本表并记录当前版本
                    version = SchemaVersion(version=_SCHEMA_VERSION, description="Initial schema")
                    session.add(version)
                    return True

                # 检查当前版本
                current = session.query(SchemaVersion).filter(
                    SchemaVersion.version == _SCHEMA_VERSION
                ).first()

                if not current:
                    # 需要迁移
                    return self._run_migrations(session)

                return True

        except Exception as e:
            print(f"检查数据库版本失败: {e}")
            return False

    def _run_migrations(self, session) -> bool:
        """运行数据库迁移"""
        try:
            # 获取当前数据库中的最高版本
            latest = session.query(SchemaVersion).order_by(
                SchemaVersion.version.desc()
            ).first()

            current_version = latest.version if latest else 0

            # 按版本运行迁移
            migrations = [
                (1, self._migrate_to_v1),
                # 未来版本添加在这里
                # (2, self._migrate_to_v2),
            ]

            for version, migration_func in migrations:
                if version > current_version:
                    print(f"运行数据库迁移到版本 {version}...")
                    migration_func(session)

                    # 记录迁移
                    new_version = SchemaVersion(
                        version=version,
                        description=migration_func.__doc__ or f"Migration to v{version}"
                    )
                    session.add(new_version)

            return True

        except Exception as e:
            print(f"数据库迁移失败: {e}")
            session.rollback()
            return False

    def _migrate_to_v1(self, session):
        """v1 迁移 - 初始Schema"""
        # 初始Schema无需额外操作
        pass

    def health_check(self) -> dict:
        """数据库健康检查"""
        try:
            with self.session() as session:
                # 测试连接
                session.execute(text("SELECT 1"))

                # 获取表信息
                from sqlalchemy import inspect
                inspector = inspect(self.engine)
                tables = inspector.get_table_names()

                return {
                    'healthy': True,
                    'db_type': self.db_type,
                    'tables': tables,
                    'table_count': len(tables),
                    'schema_version': _SCHEMA_VERSION
                }

        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'db_type': self.db_type
            }

    def get_table_info(self) -> dict:
        """获取所有表的信息"""
        try:
            from sqlalchemy import inspect
            inspector = inspect(self.engine)

            info = {}
            for table_name in inspector.get_table_names():
                try:
                    columns = inspector.get_columns(table_name)
                    indexes = inspector.get_indexes(table_name)
                    info[table_name] = {
                        'columns': len(columns),
                        'indexes': len(indexes),
                        'column_names': [c['name'] for c in columns]
                    }
                except Exception:
                    info[table_name] = {'error': '无法读取表信息'}

            return info

        except Exception as e:
            return {'error': str(e)}

    def vacuum(self):
        """清理数据库 - 仅 SQLite 支持"""
        if self.db_type == 'sqlite':
            from sqlalchemy import text
            with self.session() as session:
                session.execute(text("VACUUM"))
                session.commit()

    def recreate_tables(self):
        """重建所有表（危险操作！会清空数据）"""
        print("警告: 即将重建所有数据库表，这将删除所有数据！")
        confirm = input("输入 'yes' 确认: ")
        if confirm != 'yes':
            print("操作已取消")
            return

        with self.session() as session:
            # 删除所有表
            Base.metadata.drop_all(self.engine)
            session.commit()

        # 重新创建
        self._create_tables()
        print("数据库表已重建")


# ==================== 数据库工具函数 ====================

__all__ = [
    'DatabaseManager',
    'FileRecord',
    'SyncRecord',
    'CacheRecord',
    'DownloadRecord',
    'SchemaVersion',
    'get_db',
    'init_database',
    'load_db_config_from_env',
    'merge_config',
    'set_table_prefix',
    'get_table_name',
]


def get_db(config: dict = None) -> DatabaseManager:
    """获取数据库单例"""
    return DatabaseManager(config)


def init_database(config: dict) -> DatabaseManager:
    """初始化数据库"""
    db = get_db(config)
    return db
