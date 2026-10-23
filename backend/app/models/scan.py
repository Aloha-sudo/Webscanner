from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Boolean, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base
import enum


class ScanStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Project(Base):
    __tablename__ = 'projects'
    description = Column(Text, nullable=True)
    map_view = Column(JSON, nullable=True)
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    name_key = Column(String(240), nullable=False, unique=True)


class NetworkPart(Base):
    __tablename__ = 'network_parts'
    dns_defaults = Column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint('project_id','name_key'),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    name_key = Column(String(240), nullable=False)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    dns_options = Column(JSON, nullable=True)
    dns_status = Column(String(30), default='not_requested')
    dns_summary = Column(JSON, nullable=True)
    dns_job_id = Column(String(40), nullable=True)
    retry_of_id = Column(Integer, nullable=True, index=True)
    target = Column(String(255), nullable=False, index=True)
    scan_type = Column(String(50), default="quick")
    ports = Column(String(500), nullable=True)   # для custom-профиля
    comment = Column(Text, nullable=True)        # пользовательский комментарий
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True, index=True)
    network_part_id = Column(Integer, ForeignKey('network_parts.id'), nullable=True, index=True)
    project = Column(String(120), nullable=True, index=True)
    network = Column(String(120), nullable=True)
    source_host = Column(String(253), nullable=True)
    author = Column(String(120), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    scope_targets = Column(Text, nullable=True)
    scope_ports = Column(Text, nullable=True)
    scope_confirmed = Column(Boolean, default=False)
    exclude_ips = Column(Text, nullable=True)
    exclude_hosts = Column(Text, nullable=True)
    exclude_ports = Column(Text, nullable=True)
    speed = Column(String(20), default="normal")  # normal / fast / hard
    status = Column(Enum(ScanStatus), default=ScanStatus.QUEUED, index=True)
    progress = Column(Integer, default=0)
    stage = Column(String(100), default="queued")

    total_hosts = Column(Integer, default=0)
    total_ports = Column(Integer, default=0)
    total_services = Column(Integer, default=0)
    total_web = Column(Integer, default=0)
    total_screenshots = Column(Integer, default=0)

    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    hosts = relationship(
        "Host",
        back_populates="scan",
        cascade="all, delete-orphan",
        order_by="Host.ip",
    )
    screenshots = relationship(
        "Screenshot",
        back_populates="scan",
        cascade="all, delete-orphan",
        order_by="Screenshot.id",
    )


class Host(Base):
    dns_result = Column(JSON, nullable=True)
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    ip = Column(String(45), nullable=False, index=True)
    hostname = Column(String(255), nullable=True)
    os = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scan = relationship("Scan", back_populates="hosts")
    ports = relationship("Port", back_populates="host", cascade="all, delete-orphan")


class Port(Base):
    __tablename__ = "ports"

    id = Column(Integer, primary_key=True, index=True)
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    port = Column(Integer, nullable=False, index=True)
    protocol = Column(String(10), default="tcp")
    state = Column(String(20), default="open")
    service = Column(String(100), nullable=True)
    version = Column(String(255), nullable=True)
    banner = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    host = relationship("Host", back_populates="ports")
    service_obj = relationship("Service", back_populates="port", uselist=False, cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    port_id = Column(Integer, ForeignKey("ports.id", ondelete="CASCADE"), index=True)
    url = Column(String(500), nullable=True)
    status_code = Column(Integer, nullable=True)
    title = Column(String(500), nullable=True)
    technologies = Column(Text, nullable=True)
    ssl = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    port = relationship("Port", back_populates="service_obj")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    url = Column(String(500), nullable=False)
    minio_path = Column(String(500), nullable=False)
    status_code = Column(Integer, nullable=True)
    title = Column(String(500), nullable=True)
    technologies = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scan = relationship("Scan", back_populates="screenshots")
