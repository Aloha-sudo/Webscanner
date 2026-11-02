"""Expand grouped silent UDP results when Nmap identifies their port numbers."""
import xml.etree.ElementTree as ET


def port_numbers(text):
    values = set()
    for token in (text or '').split(','):
        if not token:
            continue
        bounds = [int(n) for n in token.split('-')]
        if len(bounds) not in (1, 2) or not 1 <= bounds[0] <= bounds[-1] <= 65535:
            raise ValueError('Invalid Nmap port range')
        values.update(range(bounds[0], bounds[-1] + 1))
    return values


def expand_udp_states(root):
    expanded = 0
    scanned = set()
    for info in root.findall('scaninfo'):
        if info.get('protocol') == 'udp':
            scanned.update(port_numbers(info.get('services')))
    for host in root.findall('host'):
        ports = host.find('ports')
        if ports is None:
            continue
        explicit = {int(p.get('portid')) for p in ports.findall('port') if p.get('protocol') == 'udp'}
        for extra in ports.findall('extraports'):
            if extra.get('state') != 'open|filtered':
                continue
            count = int(extra.get('count', '0'))
            expanded += count
            if count < 0 or expanded > 500000:
                raise ValueError('Too many grouped UDP ports')
            numbers = set()
            for reason in extra.findall('extrareasons'):
                if reason.get('proto') == 'udp':
                    numbers.update(port_numbers(reason.get('ports')))
            if not numbers and scanned and not any(e.get('state') != 'open|filtered' for e in ports.findall('extraports')):
                numbers = scanned - explicit
            if len(numbers) != count:
                raise ValueError('Nmap grouped open|filtered results without exact UDP ports; inspect the raw XML')
            for number in sorted(numbers - explicit):
                port = ET.SubElement(ports, 'port', protocol='udp', portid=str(number))
                ET.SubElement(port, 'state', state='open|filtered', reason='no-response')
                explicit.add(number)
