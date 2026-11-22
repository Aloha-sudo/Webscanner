"""Options for one explicitly requested SMB inventory; credentials are never serialized back."""
import ipaddress
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


def targets(value):
    found = {}
    for part in re.split(r'[\s,;]+', value.strip()):
        if not part:
            continue
        network = ipaddress.ip_network(part, strict=False)
        if network.num_addresses > 256:
            raise ValueError('SMB: не более 256 адресов за запуск')
        for address in network.hosts():
            if address.is_multicast or address.is_unspecified:
                raise ValueError('SMB: укажите unicast IP или подсеть')
            found[str(address)] = None
            if len(found) > 256:
                raise ValueError('SMB: не более 256 адресов за запуск')
    if not found:
        raise ValueError('SMB: укажите IP или подсеть')
    return list(found)


def valid_dns_name(value):
    # Require a name rather than an IP SPN; do not resolve or change the target IP.
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        return bool(re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value)) and all(1 <= len(label) <= 63 and not label.startswith('-') and not label.endswith('-') for label in value.split('.'))


class SmbStart(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    targets: str = Field(min_length=1, max_length=4000)
    mode: Literal['anonymous', 'credentials'] = 'anonymous'
    credential_type: Literal['password', 'ntlm', 'kerberos'] = 'password'
    aes_key: SecretStr = Field(default_factory=lambda: SecretStr(''), max_length=64)
    kdc_host: str = Field('', max_length=253)
    server_names: dict[str, str] = Field(default_factory=dict, max_length=256)
    nt_hash: SecretStr = Field(default_factory=lambda: SecretStr(''), max_length=65)
    username: str = Field('', max_length=253)
    domain: str = Field('', max_length=253)
    password: SecretStr = Field(default_factory=lambda: SecretStr(''), max_length=1024)
    browse_scope: Literal['scan','host'] = 'scan'
    spider: bool = False
    depth: int = Field(3, ge=0, le=20)
    max_entries: int = Field(10000, ge=1, le=100000)
    include_admin: bool = False

    @model_validator(mode='after')
    def check(self):
        targets(self.targets)
        self.username = self.username.strip()
        self.domain = self.domain.strip()
        self.kdc_host = self.kdc_host.strip()
        if any(any(ord(c) < 32 for c in value) for value in (self.username, self.domain)):
            raise ValueError('SMB: некорректное имя учётной записи')
        if self.mode == 'credentials' and not self.username.strip():
            raise ValueError('SMB: укажите логин')
        if '\\' in self.username:
            if self.domain or self.username.count('\\') != 1:
                raise ValueError('SMB: укажите домен отдельно или в виде DOMAIN\\user')
            self.domain, self.username = self.username.split('\\', 1)
            if not self.username or not self.domain:
                raise ValueError('SMB: укажите логин')
        if self.mode == 'credentials' and self.credential_type == 'kerberos':
            if not re.fullmatch(r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{64})', self.aes_key.get_secret_value()):
                raise ValueError('SMB: AES-ключ Kerberos должен содержать 32 или 64 hex-символа')
            if not self.domain.strip() or not self.kdc_host.strip():
                raise ValueError('SMB Kerberos: укажите домен и контроллер')
            try:
                ipaddress.ip_address(self.kdc_host)
            except ValueError:
                if not valid_dns_name(self.kdc_host):
                    raise ValueError('SMB Kerberos: некорректный адрес контроллера')
            addresses = targets(self.targets)
            if set(self.server_names) != set(addresses) or any(not valid_dns_name(v) for v in self.server_names.values()):
                raise ValueError('SMB Kerberos: для каждого IP укажите DNS-имя сервера (IP=имя)')
            self.password = SecretStr('')
        else:
            self.aes_key = SecretStr('')
            self.kdc_host = ''
            self.server_names = {}
        if self.mode == 'credentials' and self.credential_type == 'ntlm':
            if not re.fullmatch(r'(?:[0-9a-fA-F]{32}:)?[0-9a-fA-F]{32}', self.nt_hash.get_secret_value()):
                raise ValueError('SMB: укажите NT-хэш (32 hex) или LM:NT')
            self.password = SecretStr('')
        else:
            self.nt_hash = SecretStr('')
        if self.mode == 'anonymous':
            self.username = self.domain = ''
            self.password = SecretStr('')
        return self

    def public(self):
        return {**self.model_dump(exclude={'password', 'nt_hash', 'aes_key'}), 'targets': targets(self.targets)}

    def credential(self):
        return {'password': self.password, 'ntlm': self.nt_hash, 'kerberos': self.aes_key}[self.credential_type].get_secret_value()


class SmbAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['list','preview','download','permissions']
    share: str = Field(min_length=1,max_length=256)
    path: str = Field('',max_length=2048)
    directory: bool = False
    offset: int = Field(0,ge=0,le=10000)
    query: str = Field('',max_length=200)

    @model_validator(mode='after')
    def check(self):
        from app.core.smb_file_ops import checked_path
        self.path=checked_path(self.path)
        if not self.path and self.action in ('preview','download'):
            raise ValueError('SMB: выберите файл')
        if any(ord(c)<32 for c in self.share+self.query):
            raise ValueError('SMB: недопустимые символы')
        return self
