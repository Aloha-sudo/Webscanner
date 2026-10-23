"""Explicit resolver settings; resolver addresses never pass through a shell."""
import ipaddress
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class DnsOptions(BaseModel):
    enabled: bool = True
    server: str | None = Field(None, max_length=45)
    transport: Literal['auto', 'udp', 'tcp'] = 'auto'

    @field_validator('server')
    @classmethod
    def valid_server(cls, value):
        if not value or not value.strip():
            return None
        address = ipaddress.ip_address(value.strip())
        if address.is_unspecified or address.is_multicast:
            raise ValueError('Укажите unicast IP DNS-сервера')
        return str(address)


class DnsEvidence(BaseModel):
    status: Literal['resolved', 'no_record', 'unreachable', 'refused', 'dns_error', 'budget_exceeded', 'no_server']
    names: list[str] = Field(default_factory=list, max_length=16)
    server: str | None = Field(None, max_length=45)
    transport: Literal['auto', 'udp', 'tcp'] | None = None
    checked_at: str | None = Field(None, max_length=64)
    method: Literal['PTR'] = 'PTR'
    attempts: list['DnsEvidence'] = Field(default_factory=list, max_length=8)

    @field_validator('names')
    @classmethod
    def valid_names(cls, values):
        if any(not name or len(name) > 253 or any(ord(c) < 32 for c in name) for name in values):
            raise ValueError('Некорректное DNS-имя в отчёте')
        return values
