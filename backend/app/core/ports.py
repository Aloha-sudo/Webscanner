def top_ports(path='/usr/share/nmap/nmap-services', count=1000, protocol='tcp'):
    rows = []
    with open(path) as f:
        for line in f:
            fields = line.split()
            if len(fields) >= 3 and fields[1].endswith('/' + protocol) and not line.startswith('#'):
                try:
                    rows.append((float(fields[2]), int(fields[1].split('/')[0])))
                except ValueError:
                    continue
    ports = [p for _, p in sorted(rows, reverse=True)[:count]]
    if not ports:
        raise ValueError(f'Nmap {protocol.upper()} port database is empty')
    return ','.join(str(p) for p in ports)


def top_tcp_ports(path='/usr/share/nmap/nmap-services', count=1000):
    return top_ports(path, count, 'tcp')
