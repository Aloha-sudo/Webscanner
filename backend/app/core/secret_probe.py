"""Read selected saved SMB files using stdin credentials, in a bounded child."""
import json
import logging
import os
import re
from pathlib import Path
import sys
import time
from app.reports import smb
from app.secrets.engine import Detector
from app.secrets.store import write
from app.core import smb_file_ops as files
from app.core.smb_probe import safe_error
connect=files.connect

NO_CONTENT={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.zip','.rar','.7z','.png','.jpg','.jpeg','.gif','.bmp','.ico','.webp','.mp4','.avi','.mp3','.wav','.exe','.dll','.so','.msi'}
MAX_BYTES=2*1024*1024
MAX_TOTAL=50*1024*1024
MAX_FILES=500
MAX_CANDIDATES=50000
MAX_FINDINGS=1000

def size_hint(value):
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*(B|KB|MB|GB|KIB|MIB|GIB)',str(value).strip().upper())
    if not match:return 1
    factor={'B':1,'KB':1024,'KIB':1024,'MB':1024**2,'MIB':1024**2,'GB':1024**3,'GIB':1024**3}[match[2]]
    return int(float(match[1])*factor)

def candidates(root,scan_id,choices):
    for choice in choices:
        report=smb.get_report(root,scan_id,choice['report_id'])
        with smb.catalog(root,scan_id,choice['report_id']) as catalog:
            for row in catalog.execute('SELECT share,path,parent,name,kind,metadata FROM entries WHERE share=? AND kind=? ORDER BY path',[choice['share'],'file']):
                item=dict(row);item['metadata']=json.loads(item['metadata'])
                yield report,item

def scan(root,scan_id,choices,options,secret,jobdir,detector=None,connector=connect):
    detector=detector or Detector()
    stats={'considered':0,'read':0,'skipped':0,'denied':0,'bytes':0,'unsupported':0,'too_large':0,'read_limit':0,'byte_limit':0,'discarded':0,'candidate_limit':0,'finding_limit':0,'time_limit':0}
    sources=[smb.get_report(root,scan_id,choice['report_id']) for choice in choices]
    partial=any(report.get('partial') or report.get('limits') or (report.get('coverage')!='files' and report.get('format')!='netexec-spider-plus') for report in sources)
    findings=[];connection=None;current_host=None;error=None;deadline=time.monotonic()+570
    content=jobdir/'content.bin'
    previous_limit=files.MAX_DOWNLOAD
    files.MAX_DOWNLOAD=MAX_BYTES
    try:
        for report,entry in candidates(root,scan_id,choices):
            if stats['considered']>=MAX_CANDIDATES:partial=True;stats['candidate_limit']=1;break
            if time.monotonic()>deadline:partial=True;stats['time_limit']=1;break
            stats['considered']+=1
            if stats['considered']%50==0:write(jobdir,{'findings':findings,'stats':stats,'partial':partial},'progress.json')
            suffix=Path(entry['name']).suffix.lower()
            if entry['metadata'].get('reparse_point'):stats['skipped']+=1;continue
            try:
                # Metadata sizes may be human-readable; actual limit is enforced on live reads.
                estimated=size_hint(entry['metadata'].get('size'))
                check=detector.check(f"//{report['host']}/{entry['share']}/{entry['path']}",estimated)
                if check.status.name=='DISCARD':stats['skipped']+=1;stats['discarded']+=1;continue
                data=None
                if detector.needs_bytes(check):
                    reason=None
                    if suffix in NO_CONTENT and check.status.name!='CHECK_KEYS':reason='unsupported'
                    elif estimated>MAX_BYTES:reason='too_large'
                    elif stats['read']>=MAX_FILES:reason='read_limit'
                    elif stats['bytes']>=MAX_TOTAL:reason='byte_limit'
                    if reason:
                        stats['skipped']+=1;stats[reason]+=1
                        if reason!='unsupported':partial=True
                    else:
                        if current_host!=report['host']:
                            if connection:connection.close()
                            connection=None;current_host=report['host'];connection=connector(current_host,options,secret)
                        files.MAX_DOWNLOAD=min(MAX_BYTES,MAX_TOTAL-stats['bytes'])
                        result=files.operate(connection,entry['share'],entry['path'],'download',{},content)
                        size=result['size']
                        if stats['bytes']+size>MAX_TOTAL:partial=True;break
                        data=content.read_bytes();stats['bytes']+=len(data);stats['read']+=1
                found=detector.result(check,data)
                if found:findings.append({**found,'host':report['host'],'report_id':report['id'],'share':entry['share'],'path':entry['path'],'name':entry['name'],'read_confirmed':data is not None})
                if len(findings)>=MAX_FINDINGS:partial=True;stats['finding_limit']=1;break
            except (AttributeError,TypeError):error='secret_engine_error';break
            except files.FileLimit:stats['skipped']+=1;stats['byte_limit' if files.MAX_DOWNLOAD<MAX_BYTES else 'too_large']+=1;partial=True
            except Exception as exc:
                code=safe_error(exc)
                if code in ('authentication_failed','account_locked','account_disabled'):error=code;break
                stats['denied']+=1
            finally:content.unlink(missing_ok=True)
            write(jobdir,{'findings':findings,'stats':stats,'partial':partial},'progress.json')
    finally:
        files.MAX_DOWNLOAD=previous_limit
        content.unlink(missing_ok=True)
        if connection:
            try:connection.close()
            except Exception:pass
    partial=partial or stats['denied']>0
    return {'status':'failed' if error else 'partial' if partial else 'completed','error':error,'findings':findings,'stats':stats,'partial':partial}

def main():
    os.umask(0o077);logging.disable(logging.CRITICAL)
    payload=json.load(sys.stdin);jobdir=Path(sys.argv[1])
    if sys.platform.startswith('linux'):
        import ctypes,signal
        ctypes.CDLL(None).prctl(1,signal.SIGKILL)
        if os.getppid()!=payload.get('parent_pid',os.getppid()):return
    try:result=scan(payload['root'],payload['scan_id'],payload['choices'],payload['options'],payload['secret'],jobdir)
    except ValueError as exc:result={'status':'failed','error':'secret_engine_unavailable' if str(exc)=='secret_engine_unavailable' else 'secret_scan_failed'}
    except Exception:result={'status':'failed','error':'secret_scan_failed'}
    write(jobdir,result,'result.json')

if __name__=='__main__':main()
