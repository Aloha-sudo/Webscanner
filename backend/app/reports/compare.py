def compare_reports(before: dict, after: dict) -> dict:
    left = {h['ip']: h for h in before['hosts']}
    right = {h['ip']: h for h in after['hosts']}
    changes = []
    for ip in sorted(left.keys() & right.keys()):
        a, b = left[ip], right[ip]
        ap = {(p['protocol'], p['port']): p for p in a['ports']}
        bp = {(p['protocol'], p['port']): p for p in b['ports']}
        changed = []
        for key in sorted(ap.keys() & bp.keys()):
            fields = {k: {'before': ap[key].get(k), 'after': bp[key].get(k)}
                      for k in ('service','version','banner','state','url','status_code','title','technologies','ssl')
                      if ap[key].get(k) != bp[key].get(k)}
            if fields:
                changed.append({'port': key[1], 'protocol': key[0], 'fields': fields})
        metadata = {k: {'before': a.get(k), 'after': b.get(k)} for k in ('hostname','os') if a.get(k) != b.get(k)}
        added = [bp[k] for k in sorted(bp.keys()-ap.keys())]
        removed = [ap[k] for k in sorted(ap.keys()-bp.keys())]
        if added or removed or changed or metadata:
            changes.append({'ip': ip, 'added_ports': added, 'removed_ports': removed, 'changed_ports': changed, 'metadata': metadata})
    return {'added_hosts': [right[ip] for ip in sorted(right.keys()-left.keys())],
            'removed_hosts': [left[ip] for ip in sorted(left.keys()-right.keys())],
            'changed_hosts': changes, 'unchanged_hosts': len(left.keys() & right.keys())-len(changes),
            'warnings': ['Показаны различия записей. Разные цели, профили портов и неполные отчёты могут объяснять отсутствие хоста или порта.']}
