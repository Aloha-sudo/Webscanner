"""Bounded preview/download for FTP and explicitly supplied local directories."""
import json
from pathlib import Path,PurePosixPath
import sys
from app.secrets.sources import read_local,ftp_in_scope,connect_ftp
from app.core.smb_file_ops import MAX_DOWNLOAD,FileLimit,preview


def operate(options,secret,location,action,output):
    if action not in ('preview','download'):raise ValueError('invalid_action')
    if options.get('source')=='local':
        content=read_local(options,location,MAX_DOWNLOAD+1)
        if len(content)>MAX_DOWNLOAD:raise FileLimit()
        filename=Path(location).name
    elif options.get('source')=='ftp':
        target=ftp_in_scope(options,location);ftp=connect_ftp(options,secret,target.hostname,target.port or 21)
        buffer=bytearray()
        def chunk(data):
            if len(buffer)+len(data)>MAX_DOWNLOAD:raise FileLimit()
            buffer.extend(data)
        try:ftp.retrbinary('RETR '+target.path,chunk)
        finally:ftp.close()
        content=bytes(buffer);filename=PurePosixPath(target.path).name
    else:raise ValueError('source_outside_scope')
    result={'filename':filename,'size':len(content)}
    if action=='preview':result['preview']=preview(content,filename)
    else:output.write_bytes(content)
    return result


def main():
    payload=json.load(sys.stdin);directory=Path(sys.argv[1])
    try:
        data=operate(payload['options'],payload['secret'],payload['location'],payload['action'],directory/'download.bin')
        result={'status':'completed','result':data}
    except FileLimit:result={'status':'failed','error':'file_too_large'}
    except Exception as exc:
        import ftplib
        error='authentication_failed' if isinstance(exc,ftplib.error_perm) and str(exc).startswith('530') else 'source_outside_scope' if isinstance(exc,ValueError) else 'action_failed'
        result={'status':'failed','error':error}
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
