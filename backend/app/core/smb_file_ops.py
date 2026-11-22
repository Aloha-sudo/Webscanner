"""Bounded live SMB browsing and downloads. This module never writes to remote shares."""
from datetime import datetime, timezone
import io
from pathlib import PurePosixPath
import zipfile
from xml.etree import ElementTree as ET
from app.core.smb_probe import safe_error, stamp
from app.reports.smb import relative_path

MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_PREVIEW = 60000
MAX_DIRECTORY = 10000


class FileLimit(Exception):
    pass


def checked_path(path):
    if not path:
        return ''
    path = relative_path(path)
    if any(c in path for c in '*?'):
        raise ValueError('invalid_path')
    return path


def preview(content, filename):
    extension = PurePosixPath(filename).suffix.lower()
    if extension in ('.docx', '.xlsx'):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = archive.infolist()
                if len(infos) > 2000 or sum(i.file_size for i in infos) > 32 * 1024 * 1024:
                    return {'supported': False, 'reason': 'preview_limit'}
                def xml(name):
                    info = archive.getinfo(name)
                    if info.file_size > 8 * 1024 * 1024:
                        raise FileLimit()
                    data = archive.read(name)
                    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                        raise FileLimit()
                    return ET.fromstring(data)
                if extension == '.docx':
                    root = xml('word/document.xml')
                    text = '\n'.join(''.join(n.itertext()) for n in root.iter() if n.tag.endswith('}p'))
                else:
                    strings = []
                    if 'xl/sharedStrings.xml' in archive.namelist():
                        strings = [''.join(n.itertext()) for n in xml('xl/sharedStrings.xml')]
                    sheets = sorted(n for n in archive.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))[:3]
                    rows = []
                    for name in sheets:
                        rows.append(name)
                        for row in xml(name).iter():
                            if not row.tag.endswith('}row'): continue
                            cells = []
                            for cell in list(row)[:50]:
                                value = ''.join(n.text or '' for n in cell.iter() if n.tag.endswith('}v') or n.tag.endswith('}t'))
                                if cell.attrib.get('t') == 's':
                                    value = strings[int(value)] if value.isdigit() and int(value) < len(strings) else ''
                                cells.append(value)
                            rows.append('\t'.join(cells))
                            if len(rows) >= 500: break
                    text = '\n'.join(rows)
                return {'supported': True, 'text': text[:MAX_PREVIEW], 'truncated': len(text) > MAX_PREVIEW, 'format': extension[1:]}
        except (zipfile.BadZipFile, KeyError, ValueError, ET.ParseError, FileLimit, RuntimeError):
            return {'supported': False, 'reason': 'preview_unavailable'}
    allowed = {'.txt','.csv','.json','.xml','.log','.ini','.conf','.config','.cfg','.yaml','.yml','.md','.ps1','.bat','.sql','.html','.htm','.sh','.env','.py','.properties','.pem','.key','.ppk','.pub','.ovpn','.rdp','.vnc','.tf','.tfvars','.toml','.cmd'}
    if extension not in allowed and filename.lower() not in ('.env','readme','dockerfile','config','credentials','id_rsa','id_dsa','id_ecdsa','id_ed25519','.npmrc','.pypirc','.git-credentials'):
        return {'supported': False, 'reason': 'preview_unavailable'}
    raw = content[:MAX_PREVIEW*2]
    encodings = ['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'cp1251']
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if '\x00' in text: continue
            return {'supported': True, 'text': text[:MAX_PREVIEW], 'truncated': len(content)>len(raw) or len(text)>MAX_PREVIEW, 'format':'text'}
        except UnicodeError: pass
    return {'supported': False, 'reason': 'preview_unavailable'}


def connect(host, options, secret):
    from impacket.smbconnection import SMBConnection
    conn = SMBConnection(options.get('server_names', {}).get(host, host), host, sess_port=445, timeout=4)
    try:
        if options['mode'] == 'anonymous':
            conn.login('', '', '', ntlmFallback=False)
        elif options['credential_type'] == 'kerberos':
            conn.kerberosLogin(options['username'],'',options['domain'],aesKey=secret,kdcHost=options['kdc_host'],useCache=False)
        elif options['credential_type'] == 'ntlm':
            pair = secret.split(':'); lm, nt = (pair[0],pair[1]) if len(pair)==2 else ('',pair[0])
            conn.login(options['username'],'',options['domain'],lmhash=lm,nthash=nt,ntlmFallback=False)
        else:
            conn.login(options['username'],secret,options['domain'],ntlmFallback=False)
        return conn
    except Exception:
        try:conn.close()
        except Exception:pass
        raise


def verify_no_reparse(conn, share, path):
    """Reject junctions/symlinks in every supplied path component before access."""
    parts = path.split('/') if path else []
    for index, name in enumerate(parts):
        entries = conn.listPath(share, '\\'.join(parts[:index+1]))
        match = next((entry for entry in entries if entry.get_longname() == name), None)
        if match is None:
            raise ValueError('path_not_found')
        if match.get_attributes() & 0x400:
            raise ValueError('reparse_blocked')


def permissions(conn, share, path, directory=False):
    from impacket.smb3structs import (FILE_READ_DATA, FILE_WRITE_DATA, FILE_APPEND_DATA, DELETE,
        READ_CONTROL, WRITE_DAC, WRITE_OWNER, FILE_OPEN, FILE_DIRECTORY_FILE, FILE_NON_DIRECTORY_FILE,
        FILE_OPEN_REPARSE_POINT, FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE)
    checks = [('READ',FILE_READ_DATA),('WRITE',FILE_WRITE_DATA),('APPEND',FILE_APPEND_DATA),
              ('DELETE',DELETE),('READ_ACL',READ_CONTROL),('CHANGE_ACL',WRITE_DAC),('CHANGE_OWNER',WRITE_OWNER)]
    result = []
    for name, mask in checks:
        tree = handle = None
        try:
            tree = conn.connectTree(share)
            handle = conn.openFile(tree,path.replace('/','\\') or '\\',desiredAccess=mask,
                shareMode=FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,creationDisposition=FILE_OPEN,
                creationOption=(FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE)|FILE_OPEN_REPARSE_POINT)
            result.append({'right':name,'status':'allowed'})
        except Exception as exc:
            error = safe_error(exc)
            result.append({'right':name,'status':'denied' if error=='access_denied' else 'unknown','error':error})
        finally:
            if handle is not None:
                try: conn.closeFile(tree,handle)
                except Exception: pass
            if tree is not None:
                try: conn.disconnectTree(tree)
                except Exception: pass
    return {'rights':result,'checked_at':datetime.now(timezone.utc).isoformat(), 'method':'access_open'}


def operate(conn, share, path, action, request, output):
    from impacket.smb3structs import (FILE_READ_DATA, FILE_READ_ATTRIBUTES, FILE_OPEN,
        FILE_NON_DIRECTORY_FILE, FILE_OPEN_REPARSE_POINT, FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE)
    path = checked_path(path)
    verify_no_reparse(conn,share,path)
    if action == 'list':
        items = conn.listPath(share,(path.replace('/','\\')+'\\' if path else '')+'*')
        entries=[]
        for item in items:
            name=item.get_longname()
            if name in ('.','..'): continue
            try:
                if '/' in name or '\\' in name: continue
                child=checked_path(f'{path}/{name}' if path else name)
            except ValueError: continue
            entries.append({'share':share,'path':child,'parent':path,'name':name,
                'kind':'directory' if item.is_directory() else 'file',
                'metadata':{'size':f'{item.get_filesize()} B','mtime_epoch':stamp(item.get_mtime_epoch()),
                            'ctime_epoch':stamp(item.get_ctime_epoch()),'atime_epoch':stamp(item.get_atime_epoch()),
                            'reparse_point':bool(item.get_attributes()&0x400)}})
            if len(entries)>=MAX_DIRECTORY: break
        query=request.get('query','').casefold()
        entries=[e for e in entries if query in e['name'].casefold()]
        entries.sort(key=lambda e:(e['kind'],e['name'].casefold()))
        offset=request.get('offset',0)
        return {'items':entries[offset:offset+100], 'total':len(entries),'offset':offset,'limit':100,
                'partial':len(items)>=MAX_DIRECTORY,'live':True}
    if action == 'permissions':
        return permissions(conn,share,path,request.get('directory',False))
    tree = handle = None
    try:
        tree=conn.connectTree(share)
        handle=conn.openFile(tree,path.replace('/','\\'),desiredAccess=FILE_READ_DATA|FILE_READ_ATTRIBUTES,
            shareMode=FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,creationDisposition=FILE_OPEN,
            creationOption=FILE_NON_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT)
        info=conn.queryInfo(tree,handle)
        if int(info['EndOfFile']) > MAX_DOWNLOAD: raise FileLimit()
        expected=int(info['EndOfFile'])
        if expected<0:raise FileLimit()
        size=0
        with output.open('wb') as stream:
            while size < expected:
                block=conn.readFile(tree,handle,offset=size,bytesToRead=min(65536,expected-size))
                if not block or len(block)>expected-size: raise ValueError('file_changed')
                size+=len(block)
                if size>MAX_DOWNLOAD: raise FileLimit()
                stream.write(block)
        data={'size':size,'filename':PurePosixPath(path).name}
        if action=='preview': data['preview']=preview(output.read_bytes(),data['filename'])
        return data
    finally:
        if handle is not None:
            try: conn.closeFile(tree,handle)
            except Exception: pass
        if tree is not None:
            try: conn.disconnectTree(tree)
            except Exception: pass


def main():
    import json, sys
    from pathlib import Path
    payload=json.load(sys.stdin)
    directory=Path(sys.argv[1])
    conn=None
    try:
        conn=connect(payload['host'],payload['options'],payload['secret'])
        data=operate(conn,payload['share'],payload['path'],payload['action'],payload,
                     directory/'download.bin')
        result={'status':'completed','result':data}
    except FileLimit:
        result={'status':'failed','error':'file_too_large'}
    except ValueError as exc:
        allowed={'invalid_path','path_not_found','reparse_blocked','file_changed'}
        result={'status':'failed','error':str(exc) if str(exc) in allowed else 'invalid_path'}
    except Exception as exc:
        result={'status':'failed','error':safe_error(exc)}
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
