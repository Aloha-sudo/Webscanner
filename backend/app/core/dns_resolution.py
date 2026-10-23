"""Bounded PTR lookups. No database access; executed in a cancellable subprocess.

Auto probes only observed DNS endpoints, saved settings and /etc/resolv.conf.
Negative answers are not evidence that a host has no computer name.
"""
import asyncio
import ipaddress
import json
import sys
from datetime import datetime, timezone

MAX_HOSTS = 10000
MAX_SERVERS = 8
CONCURRENCY = 16
BUDGET = 60


def system_servers():
    import dns.resolver
    try:
        return [str(ipaddress.ip_address(str(item))) for item in dns.resolver.Resolver().nameservers][:3]
    except (OSError, ValueError, dns.resolver.NoResolverConfiguration):
        return []


def candidates(hosts, options, saved=None, blocked_ports=()):
    if options.get('server'):
        return [{'server': options['server'], 'source': 'manual'}]
    result = []
    if saved and saved.get('server'):
        result.append({'server': saved['server'], 'source': 'saved'})
    if 53 not in blocked_ports:
        discovered = sorted({h['ip'] for h in hosts if any(p['port'] == 53 and p.get('protocol', 'tcp') in ('tcp', 'udp') for p in h.get('ports', []))}, key=lambda ip: (ipaddress.ip_address(ip).version, int(ipaddress.ip_address(ip))))
        result += [{'server': ip, 'source': 'discovered'} for ip in discovered[:6]]
    result += [{'server': ip, 'source': 'system'} for ip in system_servers()]
    unique = {}
    for item in result:
        try:
            address = ipaddress.ip_address(item['server'])
            if address.is_unspecified or address.is_multicast:
                continue
            item = {**item, 'server': str(address)}
            unique.setdefault(item['server'], item)
        except ValueError:
            continue
    return list(unique.values())[:MAX_SERVERS]


async def query_ptr(ip, server, transport):
    import dns.asyncresolver
    import dns.exception
    import dns.rcode
    import dns.resolver
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = [server]
    resolver.timeout = .8
    resolver.lifetime = 1.2
    modes = ('udp', 'tcp') if transport == 'auto' else (transport,)
    result = {'status': 'unreachable', 'server': server, 'names': []}
    for mode in modes:
        result['transport'] = mode
        try:
            answer = await resolver.resolve_address(ip, tcp=mode == 'tcp', lifetime=1.2, search=False)
            names = sorted({str(record.target).rstrip('.') for record in answer})[:16]
            names = [name for name in names if 0 < len(name) <= 253 and not any(ord(c) < 32 for c in name)]
            return {**result, 'status': 'resolved' if names else 'no_record', 'names': names}
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {**result, 'status': 'no_record'}
        except dns.resolver.NoNameservers as exc:
            refused = any(len(error) > 4 and getattr(error[4], 'rcode', lambda: None)() == dns.rcode.REFUSED for error in exc.kwargs.get('errors', []))
            result['status'] = 'refused' if refused else 'dns_error'
            if refused:
                return result
        except (dns.exception.Timeout, OSError):
            result['status'] = 'unreachable'
        except dns.exception.DNSException:
            result['status'] = 'dns_error'
    return result


async def resolve_hosts(payload, query=query_ptr, budget=BUDGET):
    hosts = payload['hosts'][:MAX_HOSTS]
    options = payload.get('options') or {}
    transport = options.get('transport', 'auto')
    servers = candidates(payload['hosts'], options, payload.get('saved'), payload.get('blocked_ports', []))
    results = {}
    probes = []
    truncated = False
    semaphore = asyncio.Semaphore(CONCURRENCY)
    cache = {}

    async def ask(ip, server):
        key = (ip, server)
        if key not in cache:
            async with semaphore:
                cache[key] = await query(ip, server, transport)
        return dict(cache[key])

    async def work():
        if not servers or not hosts:
            return
        # Probe three actual targets. Never require a positive PTR to accept DNS:
        # NXDOMAIN/NOERROR without PTR are valid answers too.
        for offset in range(0, len(servers), 4):
            batch = servers[offset:offset + 4]
            sampled = await asyncio.gather(*(ask(h['ip'], s['server']) for s in batch for h in hosts[:3]))
            for index, server in enumerate(batch):
                answers = sampled[index * min(3, len(hosts)):(index + 1) * min(3, len(hosts))]
                probes.append({**server, 'resolved': sum(a['status'] == 'resolved' for a in answers), 'answered': sum(a['status'] in ('resolved', 'no_record', 'refused') for a in answers), 'statuses': sorted({a['status'] for a in answers})})
        ranked = sorted(probes, key=lambda s: (-s['resolved'], -s['answered'], servers.index(next(item for item in servers if item['server'] == s['server']))))
        # Explicit DNS is never silently replaced by a system resolver.
        usable = [s for s in ranked if s['answered']] or ranked[:1]

        async def resolve_one(host):
            attempts = []
            for server in usable:
                answer = await ask(host['ip'], server['server'])
                attempts.append(answer)
                if answer['status'] == 'resolved':
                    break
            chosen = next((a for a in attempts if a['status'] == 'resolved'), None)
            if not chosen:
                chosen = next((a for a in attempts if a['status'] == 'no_record'), None) or next((a for a in attempts if a['status'] == 'refused'), None) or (attempts[0] if attempts else {'status': 'unreachable', 'names': []})
            results[host['ip']] = {**chosen, 'attempts': attempts, 'checked_at': datetime.now(timezone.utc).isoformat(), 'method': 'PTR'}

        # Batches bound memory and outstanding requests for huge imports.
        for offset in range(0, len(hosts), CONCURRENCY):
            await asyncio.gather(*(resolve_one(h) for h in hosts[offset:offset + CONCURRENCY]))

    try:
        await asyncio.wait_for(work(), timeout=budget)
    except asyncio.TimeoutError:
        truncated = True
    for host in hosts:
        results.setdefault(host['ip'], {'status': 'budget_exceeded' if truncated else 'no_server', 'names': [], 'method': 'PTR'})
    counts = {}
    for result in results.values():
        counts[result['status']] = counts.get(result['status'], 0) + 1
    # Remember only a resolver that actually returned a name, not arbitrary :53.
    successful = next((s for s in servers if s['source'] != 'system' and any(r.get('server') == s['server'] and r['status'] == 'resolved' for r in results.values())), None)
    return {'hosts': results, 'summary': {'counts': counts, 'servers': probes, 'checked': len(hosts), 'skipped': max(0, len(payload['hosts']) - MAX_HOSTS), 'budget_exceeded': truncated, 'remember': {'server': successful['server'], 'transport': transport} if successful else None, 'finished_at': datetime.now(timezone.utc).isoformat()}}


if __name__ == '__main__':
    with open(sys.argv[1]) as stream:
        payload = json.load(stream)
    output = asyncio.run(resolve_hosts(payload))
    with open(sys.argv[2], 'w') as stream:
        json.dump(output, stream, ensure_ascii=False)
