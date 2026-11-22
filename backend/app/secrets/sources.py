"""Source validation and scoped reads shared by native search and file preview."""
from dataclasses import dataclass
import ftplib
import ipaddress
import os
from pathlib import Path,PurePosixPath
import re
import ssl
import stat
from urllib.parse import urlsplit,urlunsplit


def ftp_location(value):
    if len(value)>2048 or ('://' in value and not value.startswith('ftp://')):raise ValueError('FTP: укажите адрес ftp://')
    if not value.startswith('ftp://'):value='ftp://'+value
    try:parsed=urlsplit(value)
    except ValueError:raise ValueError("FTP: некорректный адрес")
    try:port=parsed.port or 21
    except ValueError:raise ValueError('FTP: некорректный порт')
    host=parsed.hostname or ''
    if parsed.scheme!='ftp' or not host or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or not 1<=port<=65535:raise ValueError('FTP: укажите адрес без учётки, например ftp://192.168.1.10/data')
    try:address=ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',host):raise ValueError('FTP: некорректный адрес')
    else:
        if address.is_multicast or address.is_unspecified:raise ValueError('FTP: укажите unicast адрес')
        host=str(address)
    path=parsed.path or '/'
    if any(ord(c)<32 for c in value) or '\\' in path or '..' in PurePosixPath(path).parts:raise ValueError('FTP: некорректный путь')
    authority=('['+host+']') if ':' in host else host.lower()
    if port!=21:authority+=':'+str(port)
    return urlunsplit(('ftp',authority,str(PurePosixPath(path)),'',''))


def local_directory(root,value):
    base=Path(root)
    if not base.is_dir() or base.is_symlink():raise ValueError('Папка для проверки не подключена к серверу')
    if len(value)>2048:raise ValueError('Укажите папку внутри secret-inputs')
    relative=PurePosixPath(value or '.')
    if relative.is_absolute() or '..' in relative.parts or '\\' in value or any(ord(c)<32 for c in value):raise ValueError('Укажите папку внутри secret-inputs')
    path=base
    for part in relative.parts:
        path=path/part
        if path.is_symlink():raise ValueError('Символические ссылки не поддерживаются')
    if not path.is_dir():raise ValueError('Папка для проверки не найдена')
    return str(path.absolute())


@dataclass
class PreparedSource:
    targets:str
    username:str
    data:dict
    secret:str
    domain:str=''
    spider:bool=False
    def public(self):return self.data
    def credential(self):return self.secret


def prepare(payload,root):
    if payload.source=='smb':
        if payload.options is None:raise ValueError('SMB: укажите IP или подсеть')
        return payload.options
    if payload.use_session or payload.scan_id:raise ValueError('Для нового источника начните самостоятельный поиск')
    if payload.options is not None:raise ValueError('Параметры SMB не относятся к этому источнику')
    if not payload.locations:raise ValueError('Укажите адрес или папку для проверки')
    if payload.source=='ftp':
        locations=list(dict.fromkeys(ftp_location(value) for value in payload.locations))
        username=payload.ftp_username.strip()
        if any(ord(c)<32 for c in username):raise ValueError('FTP: некорректный логин')
        data={'source':'ftp','targets':locations,'ftp_tls':payload.ftp_tls,'username':username,'domain':'','mode':'credentials' if username else 'anonymous'}
        return PreparedSource('\n'.join(locations),username,data,payload.ftp_password.get_secret_value())
    locations=list(dict.fromkeys(local_directory(root,value) for value in payload.locations))
    data={'source':'local','targets':locations,'local_paths':locations,'username':'','domain':'','mode':'anonymous'}
    return PreparedSource('\n'.join(payload.locations),'',data,'')


def local_relative(options,value):
    candidate=Path(value)
    for root in options.get('local_paths',[]):
        base=Path(root)
        try:relative=candidate.relative_to(base)
        except ValueError:continue
        if '..' in relative.parts:continue
        current=base
        for part in relative.parts:
            current=current/part
            if current.is_symlink():raise ValueError('source_outside_scope')
        return base,relative
    raise ValueError('source_outside_scope')


def read_local(options,value,limit):
    base,relative=local_relative(options,value)
    if not relative.parts:raise ValueError('source_outside_scope')
    fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        file_fd=os.open(relative.parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(file_fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('source_outside_scope')
            return stream.read(limit)
    finally:os.close(fd)


def ftp_in_scope(options,value):
    value=ftp_location(value);item=urlsplit(value)
    for root in options.get('targets',[]):
        base=urlsplit(ftp_location(root));prefix=base.path.rstrip('/')
        if (item.hostname,item.port or 21)==(base.hostname,base.port or 21) and (item.path==prefix or item.path.startswith(prefix+'/')):return item
    raise ValueError('source_outside_scope')


def connect_ftp(options,secret,host,port=21):
    allowed={(urlsplit(url).hostname,urlsplit(url).port or 21) for url in options['targets']}
    if (host.lower(),port) not in allowed:raise ValueError('source_outside_scope')
    ftp=ftplib.FTP_TLS(context=ssl.create_default_context(),timeout=5) if options.get('ftp_tls') else ftplib.FTP(timeout=5)
    try:
        ftp.connect(host,port);ftp.login(options.get('username') or 'anonymous',secret)
        if options.get('ftp_tls'):ftp.prot_p()
        ftp.set_pasv(True);ftp.sendcmd('TYPE I')
        return ftp
    except Exception:
        ftp.close();raise


def validate_file(options,location):
    if options.get('source')=='ftp':return ftp_in_scope(options,location)
    if options.get('source')=='local':return local_relative(options,location)
    raise ValueError('source_outside_scope')
