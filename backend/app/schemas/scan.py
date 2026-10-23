from pydantic import BaseModel, Field, computed_field, field_validator
from typing import Optional, List
from datetime import datetime
from app.schemas.dns import DnsOptions

class TeamMetadata(BaseModel):
    project_id: Optional[int] = Field(None, ge=1)
    network_part_id: Optional[int] = Field(None, ge=1)
    project: Optional[str] = Field(None, max_length=120)
    network: Optional[str] = Field(None, max_length=120)
    source_host: Optional[str] = Field(None, max_length=253)
    author: Optional[str] = Field(None, max_length=120)
    observed_at: Optional[datetime] = None
    scope_targets: Optional[str] = Field(None, max_length=4000)
    scope_ports: Optional[str] = Field(None, max_length=500)
    scope_confirmed: bool = False

    @field_validator('project','network','source_host','author')
    @classmethod
    def clean_text(cls,value):
        if value and '\x00' in value:
            raise ValueError('Нулевые байты запрещены')
        return value.strip() or None if value else None

    @field_validator('observed_at')
    @classmethod
    def require_timezone(cls,value):
        if value and value.tzinfo is None:
            raise ValueError('Время должно включать часовой пояс')
        return value

    @field_validator('scope_targets')
    @classmethod
    def valid_scope(cls,value):
        from app.core.exclusions import validate_addresses
        return validate_addresses(value)

    @field_validator('scope_ports')
    @classmethod
    def valid_scope_ports(cls,value):
        return ScanCreate.valid_ports(value) if value else None


class ScanCreate(TeamMetadata):
    dns_options: Optional[DnsOptions] = None
    target: str = Field(..., description="IP, CIDR или домен")
    scan_type: str = Field(
        "quick",
        description="quick, top100, top1000, web, full, custom",
    )
    ports: Optional[str] = Field(
        None,
        description="Список портов для custom: '22,80,443,8000-8100'",
    )
    comment: Optional[str] = Field(
        None,
        description="Пользовательский комментарий к скану",
        max_length=1000,
    )
    speed: str = Field(
        "normal",
        description="Скорость rustscan: normal, fast, hard",
    )

    exclude_ips: Optional[str] = Field(None, max_length=4000)
    exclude_hosts: Optional[str] = Field(None, max_length=4000)
    exclude_ports: Optional[str] = Field(None, max_length=4000)

    @field_validator('exclude_ips')
    @classmethod
    def valid_exclude_ips(cls, value):
        from app.core.exclusions import validate_addresses
        return validate_addresses(value)

    @field_validator('exclude_hosts')
    @classmethod
    def valid_exclude_hosts(cls, value):
        from app.core.exclusions import validate_hosts
        return validate_hosts(value)

    @field_validator('exclude_ports')
    @classmethod
    def valid_exclude_ports(cls, value):
        from app.core.exclusions import excluded_ports, tokens
        excluded_ports(value)
        return ','.join(tokens(value)) or None

    @field_validator('target')
    @classmethod
    def valid_target(cls, value):
        import ipaddress
        import re
        value = value.strip()
        if not value or len(value) > 253:
            raise ValueError('Укажите IP, CIDR или домен длиной до 253 символов')
        try:
            network = ipaddress.ip_network(value, strict=False)
            if network.num_addresses > 65536:
                raise ValueError('Максимум 65536 адресов в одном скане')
            # Current scan commands and URL handling only support IPv4.
            if network.version != 4:
                raise ValueError('Активное IPv6-сканирование пока не поддерживается')
            return value
        except ValueError as exc:
            if ':' in value or '/' in value or re.fullmatch(r'[0-9.]+', value):
                raise ValueError(str(exc))
        if not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', value):
            raise ValueError('Некорректный домен')
        return value

    @field_validator('ports')
    @classmethod
    def valid_ports(cls, value):
        import re
        if value is None:
            return value
        if len(value) > 500 or not re.fullmatch(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*', value):
            raise ValueError('Формат портов: 22,80,443,8000-8100; до 500 символов')
        count = 0
        for part in value.split(','):
            numbers = [int(n) for n in part.split('-')]
            if any(n < 1 or n > 65535 for n in numbers) or numbers[0] > numbers[-1]:
                raise ValueError('Порты должны быть в диапазоне 1–65535, диапазоны по возрастанию')
            count += numbers[-1] - numbers[0] + 1
        if ',' in value and count > 10000:
            raise ValueError('Для больших диапазонов используйте один диапазон или профиль Full')
        return value

    class Config:
        json_schema_extra = {
            "example": {
                "target": "127.0.0.1",
                "scan_type": "full"
            }
        }


class ServiceResponse(BaseModel):
    id: int
    url: Optional[str] = None
    status_code: Optional[int] = None
    title: Optional[str] = None
    technologies: Optional[str] = None
    ssl: bool = False

    class Config:
        from_attributes = True


class PortResponse(BaseModel):
    id: int
    port: int
    protocol: str
    state: str
    service: Optional[str] = None
    version: Optional[str] = None
    banner: Optional[str] = None
    service_obj: Optional[ServiceResponse] = None

    class Config:
        from_attributes = True


class HostResponse(BaseModel):
    dns_result: Optional[dict] = None
    id: int
    ip: str
    hostname: Optional[str] = None
    os: Optional[str] = None
    ports: List[PortResponse] = []

    class Config:
        from_attributes = True


class ScreenshotResponse(BaseModel):
    id: int
    url: str
    minio_path: str
    status_code: Optional[int] = None
    title: Optional[str] = None
    technologies: Optional[str] = None

    class Config:
        from_attributes = True


class ScanResponse(TeamMetadata):
    dns_options: Optional[DnsOptions] = None
    dns_status: Optional[str] = None
    dns_summary: Optional[dict] = None
    id: int
    retry_of_id: Optional[int] = None
    target: str
    scan_type: str
    ports: Optional[str] = None
    comment: Optional[str] = None
    exclude_ips: Optional[str] = None
    exclude_hosts: Optional[str] = None
    exclude_ports: Optional[str] = None
    speed: str = "normal"
    status: str
    progress: int
    stage: str
    total_hosts: int
    total_ports: int
    total_services: int
    total_web: int
    total_screenshots: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def duration_seconds(self) -> Optional[int]:
        """Длительность: от started_at до finished_at (или now для running)."""
        if not self.started_at:
            return None
        end = self.finished_at
        if end is None:
            from datetime import datetime as _dt, timezone
            end = _dt.now(timezone.utc)
        try:
            return int((end - self.started_at).total_seconds())
        except Exception:
            return None


class ScanUpdate(TeamMetadata):
    comment: Optional[str] = Field(None, max_length=1000)


class ScanListResponse(BaseModel):
    total: int
    scans: List[ScanResponse]


class ScanDetailResponse(ScanResponse):
    hosts: List[HostResponse] = []
    screenshots: List[ScreenshotResponse] = []


class ProjectDelete(BaseModel):
    delete_reports: bool = False
    project: str = Field(..., min_length=1, max_length=120)
    expected_count: int = Field(..., ge=1)


class CatalogName(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)

class MoveReports(BaseModel):
    report_ids: List[int] = Field(..., min_length=1, max_length=500)
    project_id: int = Field(..., ge=1)
    network_part_id: int = Field(..., ge=1)
