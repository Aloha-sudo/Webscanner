"""Normalize ProjectDiscovery httpx records before matching database ports."""
from app.core.text import database_text
import ipaddress
from urllib.parse import urlsplit


def normalize_result(record, target_addresses=None):
    if record.get('failed'):
        return None
    url = record.get('url') or record.get('input')
    if not url:
        return None
    try:
        parsed = urlsplit(url)
        port = int(record.get('port') or parsed.port or (443 if parsed.scheme == 'https' else 80))
        if parsed.scheme not in ('http', 'https') or not 1 <= port <= 65535:
            return None
    except (ValueError, TypeError):
        return None
    ip = None
    addresses = record.get('a') or []
    if not isinstance(addresses, list):
        addresses = []
    candidates = [record.get('host_ip'), record.get('host'), parsed.hostname]
    # A single known address can associate fallback results without another DNS lookup.
    known = (target_addresses or {}).get(parsed.hostname, [])
    if len(known) == 1:
        candidates.extend(known)
    if len(addresses) == 1:
        candidates.extend(addresses)
    for candidate in candidates:
        try:
            ip = str(ipaddress.ip_address(str(candidate)))
            break
        except ValueError:
            continue
    if ip is None:
        return None
    technologies = record.get('tech') or record.get('technologies') or []
    return {'ip':ip, 'port':port, 'url':database_text(url)[:500], 'title':database_text(str(record['title']))[:500] if record.get('title') else None,
            'status_code':record.get('status_code'), 'technologies':technologies, 'ssl':parsed.scheme=='https'}
