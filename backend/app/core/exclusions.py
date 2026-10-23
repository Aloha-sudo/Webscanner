import ipaddress
import re
import socket


def tokens(value):
    return [s for s in re.split(r'[,;\s]+', value or '') if s]


def validate_addresses(value):
    values = tokens(value)
    if len(values) > 256:
        raise ValueError('Максимум 256 исключений адресов')
    for entry in values:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError as exc:
            raise ValueError(f'Некорректный IP/CIDR: {entry}') from exc
        if network.version != 4:
            raise ValueError('Исключения активного сканирования поддерживают IPv4')
    return ','.join(values) or None


def validate_hosts(value):
    values = tokens(value)
    if len(values) > 100:
        raise ValueError('Максимум 100 исключений имён хостов')
    for entry in values:
        if len(entry)>253 or not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',entry):
            raise ValueError(f'Некорректное имя хоста: {entry}')
    return ','.join(values).lower() or None


def excluded_ports(value):
    result=set()
    for token in tokens(value):
        if not re.fullmatch(r'\d+(?:-\d+)?',token):
            raise ValueError('Исключения портов: 22,80,8000-8100')
        numbers=[int(n) for n in token.split('-')]
        if not 1 <= numbers[0] <= numbers[-1] <= 65535:
            raise ValueError('Исключённые порты должны быть от 1 до 65535; диапазон по возрастанию')
        result.update(range(numbers[0],numbers[-1]+1))
        if len(result)>10000:
            raise ValueError('Максимум 10000 исключённых портов')
    return result


def resolve_ipv4(host):
    try:
        return sorted({ipaddress.ip_address(r[4][0]) for r in socket.getaddrinfo(host,None,socket.AF_INET,socket.SOCK_STREAM)}, key=int)
    except socket.gaierror as exc:
        raise ValueError(f'Не удалось разрешить имя {host}. Скан не запущен, чтобы не нарушить исключения.') from exc


def allowed_targets(target, exclude_ips=None, exclude_hosts=None, resolver=resolve_ipv4):
    networks=[ipaddress.ip_network(x,strict=False) for x in tokens(validate_addresses(exclude_ips))]
    for host in tokens(validate_hosts(exclude_hosts)):
        addresses=resolver(host)
        if not addresses:
            raise ValueError(f'Для исключённого хоста {host} не найдены IPv4-адреса')
        networks.extend(ipaddress.ip_network(f'{ip}/32') for ip in addresses)
    try:
        net=ipaddress.ip_network(target,strict=False)
        if net.version!=4 or net.num_addresses>65536:
            raise ValueError('Неподдерживаемая сеть')
        candidates=net.hosts()
    except ValueError:
        candidates=resolver(target)
    result=[str(ip) for ip in candidates if not any(ip in n for n in networks)]
    if not result:
        raise ValueError('Все целевые адреса исключены: сканирование не запущено')
    return result
