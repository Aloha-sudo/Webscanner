"""The installed snaffler-ng runner, with redacted persistence and scoped auth.

No pre-collected file list or WebScanner filename/content classifier is used.
"""
from contextlib import closing
import ipaddress
import json
import logging
from pathlib import Path
import sqlite3
import threading
from app.secrets import store


def configuration(options,path,fast=True,max_depth=None,share_names=(),exclude_shares=(),local_paths=(),tuning=None):
    from snaffler.config.configuration import SnafflerConfiguration,FAST_MODE_EXCLUSIONS
    from snaffler.classifiers.default_rules import get_default_rules
    from snaffler.classifiers.rules import EnumerationScope
    tuning=tuning or {}
    cfg=SnafflerConfiguration()
    cfg.auth.username=options.get('username','');cfg.auth.domain=options.get('domain') or None
    cfg.auth.kerberos=options.get('credential_type')=='kerberos'
    source=options.get('source','smb')
    cfg.targets.computer_targets=list(options.get('targets',[])) if source=='smb' and not local_paths else []
    cfg.targets.local_targets=list(options.get('local_paths',[])) if source=='local' else list(local_paths)
    cfg.targets.ftp_targets=list(options.get('targets',[])) if source=='ftp' else []
    cfg.targets.ftp_tls=options.get('ftp_tls',False)
    cfg.targets.exclude_share=list(dict.fromkeys(['IPC$',*exclude_shares]))
    cfg.targets.share_filter=list(share_names)
    cfg.targets.check_writable=False
    cfg.scanning.snaffle=False
    cfg.scanning.max_depth=max_depth
    cfg.scanning.max_file_bytes=tuning.get('max_file_mb',10)*1024*1024
    cfg.scanning.max_read_bytes=tuning.get('read_mb',2)*1024*1024
    threads=tuning.get('threads',60)
    cfg.advanced.max_threads=threads
    cfg.advanced.share_threads=max(1,threads//3)
    cfg.advanced.tree_threads=max(1,threads//3)
    cfg.advanced.file_threads=max(1,threads//3)
    cfg.state.state_db=str(path/'engine.sqlite3')
    cfg.output.to_file=False;cfg.web.enabled=False
    if fast:
        cfg.targets.exclude_unc=list(FAST_MODE_EXCLUSIONS)
        cfg.advanced.max_tree_threads_per_share=5
    cfg.targets.exclude_unc.extend(value.replace("\\","/") for value in tuning.get("exclude_paths",[]))
    rules=get_default_rules()
    for scope,attribute in [(EnumerationScope.SHARE_ENUMERATION,'share'),(EnumerationScope.DIRECTORY_ENUMERATION,'directory'),(EnumerationScope.FILE_ENUMERATION,'file'),(EnumerationScope.CONTENTS_ENUMERATION,'content'),(EnumerationScope.POST_MATCH,'postmatch')]:
        setattr(cfg.rules,attribute,[rule for rule in rules if rule.enumeration_scope==scope])
    cfg.validate()
    return cfg


def parse_path(value):
    value=value.replace('\\','/')
    if not value.startswith('//'):return None
    parts=value[2:].split('/',2)
    if len(parts)!=3 or not all(parts):return None
    return {'host':parts[0],'share':parts[1],'path':parts[2],'name':parts[2].split('/')[-1]}


def format_finding(row):
    from urllib.parse import urlsplit
    raw=row['file_path']
    parsed=parse_path(raw);source='smb' if parsed else 'local'
    if raw.startswith('ftp://'):
        url=urlsplit(raw);source='ftp';parsed={'host':url.hostname,'share':str(url.port or 21),'path':url.path,'name':url.path.split('/')[-1]}
    return {'source':source,'location':raw,'id':row['finding_id'],**(parsed or {'host':'','share':'','path':row['file_path'],'name':Path(row['file_path']).name}),
            'rule':row['rule_name'],'severity':row['triage'],'kind':row['context'] if row['context'] in ('name','content') else 'name',
            'evidence':'[redacted]','size':row['size']}


def read_findings(path,query='',offset=0,limit=100):
    database=path/'engine.sqlite3'
    if database.is_symlink() or not database.is_file():return {'items':[],'total':0,'offset':offset,'limit':limit}
    import fnmatch
    needle=query.strip().casefold()
    wildcard='*' in needle or '?' in needle
    import re,time
    pattern=re.compile(fnmatch.translate(needle.replace('[','[[]'))) if wildcard else None
    def matches(file_path,rule):
        values=[file_path.casefold(),file_path.replace('\\','/').split('/')[-1].casefold(),rule.casefold()]
        if not needle:return 1
        if wildcard:
            return int(any(pattern.fullmatch(value) for value in values))
        return int(any(needle in value for value in values))
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.row_factory=sqlite3.Row;db.create_function('matches_finding',2,matches)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='finding'").fetchone():return {'items':[],'total':0,'offset':offset,'limit':limit}
        deadline=time.monotonic()+5
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        total=db.execute('SELECT count(*) FROM finding WHERE matches_finding(file_path,rule_name)').fetchone()[0]
        rows=db.execute("SELECT * FROM finding WHERE matches_finding(file_path,rule_name) ORDER BY CASE triage WHEN 'Black' THEN 3 WHEN 'Red' THEN 2 WHEN 'Yellow' THEN 1 ELSE 0 END DESC,file_path LIMIT ? OFFSET ?",[limit,offset]).fetchall()
        return {'items':[format_finding(row) for row in rows],'total':total,'offset':offset,'limit':limit}


def finding(path,finding_id):
    database=path/'engine.sqlite3'
    if database.is_symlink() or not database.is_file():raise FileNotFoundError('secret_job_missing')
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT * FROM finding WHERE finding_id=?',[finding_id]).fetchone()
    if not row:raise FileNotFoundError('secret_job_missing')
    return format_finding(row)


def run_native(options,secret,path,fast=True,max_depth=None,share_names=(),exclude_shares=(),local_paths=(),tuning=None):
    from unittest.mock import patch
    from snaffler.resume.scan_state import SQLiteStateStore
    # Some Kali Impacket builds expose this access mask only in smb3structs.
    from impacket import smb as legacy_smb,smb3structs
    with patch.object(legacy_smb,'FILE_READ_ATTRIBUTES',smb3structs.FILE_READ_ATTRIBUTES,create=True):
        from snaffler.engine import runner as runner_module
    from snaffler.accessors.smb_file_accessor import SMBFileAccessor
    from snaffler.accessors.local_file_accessor import LocalFileAccessor
    from app.secrets.sources import connect_ftp,read_local,local_relative,ftp_in_scope
    from snaffler.accessors.ftp_file_accessor import FTPFileAccessor
    from snaffler.discovery.local_tree_walker import LocalTreeWalker
    from snaffler.discovery.ftp_tree_walker import FTPTreeWalker
    from app.core.smb_file_ops import connect
    from app.core.smb_probe import safe_error
    tuning=tuning or {}
    lock=threading.Lock();stats={'read':0,'bytes':0,'denied':0,'volume_limit':0,'read_limit':0};auth_error=[None]
    reserved=[0];attempts=[0];capacity=threading.Condition(lock)
    budget=tuning.get('total_read_mb');budget=budget*1024*1024 if budget is not None else None
    read_cap=tuning.get('max_reads')
    class RedactedStore(SQLiteStateStore):
        def store_finding(self,finding_id,file_path,triage,rule_name,match_text=None,context=None,size=None,mtime=None,found_at=None):
            return super().store_finding(finding_id,file_path,triage,rule_name,match_text='[redacted]',context='content' if context else 'name',size=size,mtime=mtime,found_at=found_at)
    allowed=set(options.get('targets',[]))
    aliases={name.casefold():host for host,name in options.get('server_names',{}).items()}
    def scoped_connect(_transport,target,timeout=None):
        host=aliases.get(str(target).casefold(),str(target))
        try:host=str(ipaddress.ip_address(host.strip('[]')))
        except ValueError:raise ValueError('target_outside_scope')
        if host not in allowed:raise ValueError('target_outside_scope')
        if auth_error[0]:raise ValueError('authentication_stopped')
        try:return connect(host,options,secret)
        except Exception as exc:
            code=safe_error(exc)
            if code in ('authentication_failed','account_locked','account_disabled'):auth_error[0]=code
            raise
    def scoped_ftp(_transport,host,port=21):
        if options.get('source')!='ftp':raise ValueError('source_outside_scope')
        if auth_error[0]:raise ValueError('authentication_stopped')
        try:return connect_ftp(options,secret,host,port)
        except Exception as exc:
            import ftplib
            if isinstance(exc,ftplib.error_perm) and str(exc).startswith('530'):auth_error[0]='authentication_failed'
            raise
    original_smb=SMBFileAccessor.read;original_local=LocalFileAccessor.read
    original_ftp_read=FTPFileAccessor.read;original_ftp_walk=FTPTreeWalker.walk_directory
    def ftp_read(accessor,file_path,max_bytes=None):
        ftp_in_scope(options,file_path)
        return original_ftp_read(accessor,file_path,max_bytes)
    def ftp_walk(walker,dir_path,on_file=None,on_dir=None,cancel=None):
        ftp_in_scope(options,dir_path)
        def guarded(callback):
            def invoke(value,*args):
                try:ftp_in_scope(options,value)
                except ValueError:return
                if callback:callback(value,*args)
            return invoke
        result=original_ftp_walk(walker,dir_path,guarded(on_file),guarded(on_dir),cancel)
        filtered=[]
        for value in result:
            try:ftp_in_scope(options,value)
            except ValueError:continue
            filtered.append(value)
        return filtered
    original_walk=LocalTreeWalker.walk_directory
    def local_read(accessor,file_path,max_bytes=None):
        if options.get('source')=='local':return read_local(options,file_path,max_bytes)
        return original_local(accessor,file_path,max_bytes)
    def local_walk(walker,dir_path,on_file=None,on_dir=None,cancel=None):
        if options.get('source')!='local':return original_walk(walker,dir_path,on_file,on_dir,cancel)
        local_relative(options,dir_path)
        def file_callback(value,*args):
            try:local_relative(options,value)
            except ValueError:return
            if on_file:on_file(value,*args)
        return original_walk(walker,dir_path,file_callback,on_dir,cancel)

    def reader(original):
        def read(accessor,file_path,max_bytes=None):
            requested=max_bytes if max_bytes is not None else tuning.get('read_mb',2)*1024*1024
            with capacity:
                while budget is not None and reserved[0]>0 and budget-stats['bytes']-reserved[0]<requested:capacity.wait()
                if read_cap is not None and attempts[0]>=read_cap:
                    stats['read_limit']+=1;return None
                allowance=requested if budget is None else min(requested,max(0,budget-stats['bytes']-reserved[0]))
                if allowance<=0:
                    stats['volume_limit']+=1;return None
                reserved[0]+=allowance;attempts[0]+=1
            try:
                data=original(accessor,file_path,max_bytes=allowance)
                with lock:
                    if data is not None:
                        stats['read']+=1;stats['bytes']+=len(data)
                        if allowance<requested and len(data)>=allowance:stats['volume_limit']+=1
                    else:stats['denied']+=1
                return data
            except Exception:
                with lock:stats['denied']+=1
                raise
            finally:
                with capacity:
                    reserved[0]-=allowance;capacity.notify_all()
        return read
    class ScopedRunner(runner_module.SnafflerRunner):
        def _validate_credentials(self):
            try:return super()._validate_credentials()
            except SystemExit:
                # CIDRs commonly start with a router that has no SMB service.
                # Keep native per-host discovery; a real auth rejection still stops.
                if len(allowed)>1 and not auth_error[0]:return
                raise
    cfg=configuration(options,path,fast,max_depth,share_names,exclude_shares,local_paths,tuning)
    stop=threading.Event();controller=None;old_logging=logging.root.manager.disable
    def snapshot():
        if controller is None:return
        progress=controller.progress.snapshot()
        with lock:current=dict(stats)
        current.update(considered=progress['files_scanned'],files_total=progress['files_total'],hosts=progress['computers_done'],shares=progress['shares_found'])
        page=read_findings(path,limit=100)
        store.write(path,{'phase':'analyzing' if progress['files_total'] else 'discovering','stats':current,'findings':page['items'],'finding_count':page['total']},'progress.json')
    def progress_loop():
        while not stop.wait(.5):
            try:snapshot()
            except (sqlite3.Error,OSError):pass
    thread=None;error=None
    logging.disable(logging.CRITICAL)
    try:
        with patch.object(runner_module,'SQLiteStateStore',RedactedStore),patch('snaffler.transport.smb.SMBTransport.connect',scoped_connect),patch.object(SMBFileAccessor,'read',reader(original_smb)),patch.object(LocalFileAccessor,'read',reader(local_read)),patch.object(FTPFileAccessor,'read',reader(ftp_read)),patch.object(FTPTreeWalker,'walk_directory',ftp_walk),patch('snaffler.transport.ftp.FTPTransport.connect',scoped_ftp),patch.object(LocalTreeWalker,'walk_directory',local_walk):
            controller=ScopedRunner(cfg)
            thread=threading.Thread(target=progress_loop,daemon=True);thread.start()
            try:controller.execute()
            except SystemExit:error=auth_error[0] or 'native_connection_failed'
            finally:stop.set()
            if thread:thread.join(timeout=2)
            snapshot()
            if auth_error[0]:error=auth_error[0]
    finally:
        stop.set()
        if thread:thread.join(timeout=2)
        logging.disable(old_logging)
    page=read_findings(path,limit=100)
    progress=json.loads((path/'progress.json').read_text()) if (path/'progress.json').exists() else {'stats':stats}
    if not error and not progress['stats'].get('shares') and not local_paths and options.get('source')!='local':error='no_readable_files'
    limited=bool(progress['stats'].get('volume_limit') or progress['stats'].get('read_limit'))
    return {**progress,'partial':limited,'status':'failed' if error else 'partial' if limited else 'completed','phase':'finished','error':error,'findings':page['items'],'finding_count':page['total'],'engine':'snaffler-ng'}
