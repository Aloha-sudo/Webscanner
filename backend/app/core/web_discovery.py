"""Web candidates and a TLS-tolerant fallback for private admin panels."""
import http.client
import json
import ipaddress
import re
import ssl
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


def target_hostname(target):
    """Only the explicit scan target is a virtual host, never a guessed PTR name."""
    if not target:
        return None
    try:
        ipaddress.ip_network(target, strict=False)
        return None
    except ValueError:
        pass
    if not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', target):
        return None
    return target.lower()


def extract_urls(path, web_ports, target=None):
    urls = []
    hostname = target_hostname(target)
    for host in ET.parse(path).getroot().findall('host'):
        ip = next((a.get('addr') for a in host.findall('address') if a.get('addrtype') in ('ipv4', 'ipv6')), None)
        if not ip:
            continue
        for port in host.findall('ports/port'):
            state = port.find('state')
            if port.get('protocol', 'tcp') != 'tcp' or state is None or state.get('state') != 'open':
                continue
            number = int(port.get('portid'))
            service = port.find('service')
            name = service.get('name', '').lower() if service is not None else ''
            tunnel = service.get('tunnel', '') if service is not None else ''
            if number not in web_ports and 'http' not in name:
                continue
            address = hostname or (f'[{ip}]' if ':' in ip else ip)
            schemes = ('https', 'http') if tunnel == 'ssl' or 'https' in name or number in (443,8006,8443,9443) else ('http','https')
            urls.extend(f'{scheme}://{address}:{number}' for scheme in schemes)
    return list(dict.fromkeys(urls))


def probe(url, timeout=5):
    target = urlsplit(url)
    # Only this discovery request permits untrusted certificates.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    request = urllib.request.Request(url, headers={'User-Agent':'WebScanner/0.1'})
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc  # 401/403 still confirms a web service.
    with response:
        body = response.read(262144).decode('utf-8', errors='replace')
        title = re.search(r'<title\b[^>]*>(.*?)</title\s*>', body, re.I | re.S)
        return {'url':url, 'host':target.hostname, 'port':target.port or (443 if target.scheme=='https' else 80),
                'status_code':response.code, 'title':re.sub(r'\s+',' ',title[1]).strip() if title else None,
                'tech':['Proxmox VE'] if 'proxmox virtual environment' in body.lower() else []}


def supplement_httpx(path, urls, check_cancelled=lambda: None):
    records = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    found = {(urlsplit(r.get('url','')).hostname, urlsplit(r.get('url','')).port) for r in records if r.get('url') and not r.get('failed')}
    for url in urls:
        check_cancelled()
        target = urlsplit(url)
        key = (target.hostname, target.port)
        if key in found:
            continue
        try:
            record = probe(url)
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
            continue
        records.append(record)
        with open(path, 'a') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        found.add(key)
    with open(path,'w') as f:
        for record in records:
            f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return list(dict.fromkeys(r['url'] for r in records if r.get('url') and not r.get('failed')))


if __name__ == '__main__':
    import sys
    with open(sys.argv[2]) as f:
        candidates = [line.strip() for line in f if line.strip()]
    print(json.dumps(supplement_httpx(sys.argv[1], candidates)))
