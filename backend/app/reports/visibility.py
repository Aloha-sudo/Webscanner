"""Evidence matrix. Missing records do not establish reachability."""
import ipaddress
import json


def port_in_scope(number, text):
    for part in (text or '').split(','):
        if part:
            bounds=[int(x) for x in part.split('-')]
            if bounds[0] <= number <= bounds[-1]:
                return True
    return False


def host_in_scope(ip, text):
    address=ipaddress.ip_address(ip)
    return any(address in ipaddress.ip_network(n,strict=False) for n in (text or '').split(',') if n)


def build_visibility(reports, whole_project=False, merge_parts=False):
    projects={r.get('project_id') or r['project'] for r in reports}
    contexts={(r.get('project_id') or r['project'],r.get('network_part_id') or r['network']) for r in reports}
    if len(projects)>1 or (not whole_project and len(contexts)>1):
        raise ValueError('Нельзя смешивать разные проекты; разные части сети доступны в режиме «Весь проект»')
    rows={};observations=[]
    for report in reports:
        part=report.get('network_part_id') or report['network']
        identity=None if merge_parts else part
        found={}
        for host in report['hosts']:
            for port in [{'port':0,'protocol':'host','service':None}]+host['ports']:
                key=(identity,host['ip'],port.get('protocol','tcp'),port['port'])
                found[key]=port
                row=rows.setdefault(key,{'device_id':json.dumps([identity,host['ip']],ensure_ascii=False),'ip':host['ip'],'protocol':key[2],'port':key[3],
                                        'network':report['network'],'network_part_id':report.get('network_part_id'),'parts':[], 'hostname':host.get('hostname'),'cells':[]})
                if report['network'] not in row['parts']:row['parts'].append(report['network'])
                if not row['hostname'] and host.get('hostname'):row['hostname']=host['hostname']
        observations.append(found)
    if len(rows)>5000:
        raise ValueError('Больше 5000 строк. Выберите меньше отчётов')
    for key,row in rows.items():
        if len(row['parts'])>1:row['network']=' / '.join(row['parts'])
        for report,found in zip(reports,observations):
            item=found.get(key);state='found' if item else 'unknown'
            same_part=merge_parts or key[0]==(report.get('network_part_id') or report['network'])
            if same_part and not report.get('exclude_hosts') and key[2]!='host' and not item and report.get('scope_confirmed') and report.get('scope_targets') and report.get('scope_ports'):
                state='not_found' if not host_in_scope(key[1],report.get('exclude_ips')) and not port_in_scope(key[3],report.get('exclude_ports')) and key[2]=='tcp' and host_in_scope(key[1],report['scope_targets']) and port_in_scope(key[3],report['scope_ports']) else 'not_tested'
            row['cells'].append({'report_id':report['id'],'state':state,'service':item.get('service') if item else None,'version':item.get('version') if item else None})
    columns=[{k:r.get(k) for k in ('id','target','source_host','author','observed_at','created_at','scope_confirmed','scope_targets','scope_ports','network','network_part_id')} for r in reports]
    result=sorted(rows.values(),key=lambda r:(r['network'],ipaddress.ip_address(r['ip']).version,int(ipaddress.ip_address(r['ip'])),r['protocol'],r['port']))
    warnings=['Связи показывают обнаруженные сервисы, а не физические соединения или маршруты. Отсутствие записи без подтверждённой области проверки — «Нет данных».']
    if whole_project:
        warnings.append('Одинаковые IP между частями объединены по вашему выбору.' if merge_parts else 'Одинаковые IP в разных частях сети показаны отдельно. Для сравнения общих устройств включите «Общая адресация» только если IP обозначают одни и те же устройства.')
    return {'columns':columns,'rows':result,'warnings':warnings,'whole_project':whole_project,'merge_parts':merge_parts}
