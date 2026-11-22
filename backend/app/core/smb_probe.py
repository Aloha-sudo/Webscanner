"""Read-only SMB inventory, isolated in a bounded child process by smb_jobs.

Credentials arrive on stdin, never argv, disk, stdout or report exceptions.
"""
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from app.reports.smb import relative_path


def safe_error(exc):
    for method in ('getErrorCode', 'get_error_code'):
        try:
            code = int(getattr(exc, method)())
            return {6: 'kerberos_principal_unknown', 7: 'kerberos_spn_unknown', 14: 'kerberos_encryption_unsupported',
                    18: 'account_disabled', 23: 'kerberos_key_expired', 24: 'authentication_failed',
                    37: 'kerberos_clock_skew', 41: 'kerberos_key_mismatch', 0xC0000022: 'access_denied', 0xC000006D: 'authentication_failed',
                    0xC000006A: 'authentication_failed', 0xC0000064: 'authentication_failed',
                    0xC0000234: 'account_locked', 0xC0000072: 'account_disabled',
                    0xC00000CC: 'share_not_found'}.get(code, f'NTSTATUS_0x{code:08X}')
        except (AttributeError, TypeError, ValueError):
            pass
    # Exception text from a library can contain credentials; never retain it.
    return 'connection_error'


def stamp(value):
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def signing_evidence(connection):
    """SMB 3.1.1 client signing policy is not the server's advertised requirement."""
    dialect = connection.getDialect()
    client_policy = bool(connection.isSigningRequired())
    if isinstance(dialect, int) and dialect >= 0x300:
        state = connection.getSMBServer()._Connection
        security_mode = state.get('ServerSecurityMode')
        if not isinstance(security_mode, int):
            return {'signing_required': None, 'client_signing_required': client_policy,
                    'signing_source': 'unknown'}
        return {'signing_required': bool(security_mode & 0x2),
                'client_signing_required': client_policy, 'signing_source': 'server_security_mode'}
    return {'signing_required': client_policy, 'client_signing_required': client_policy,
            'signing_source': 'negotiation'}


def write_access(connection, share_name, check=lambda: None):
    """Open the existing share root with access masks; never create/write/change ACLs."""
    from impacket.smb3structs import (GENERIC_WRITE, FILE_ADD_FILE, FILE_ADD_SUBDIRECTORY,
        WRITE_DAC, WRITE_OWNER, FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE,
        FILE_OPEN, FILE_DIRECTORY_FILE)
    checks = [(GENERIC_WRITE, 'WRITE'), (FILE_ADD_FILE, 'WRITE'),
              (FILE_ADD_SUBDIRECTORY, 'WRITE (SUBDIR)'), (WRITE_DAC, 'WRITE (ACL)'),
              (WRITE_OWNER, 'WRITE (OWNER)')]
    labels, errors, evidence = [], [], []
    denied = 0
    for mask, label in checks:
        if label in labels:
            continue
        check()
        tree = handle = None
        try:
            tree = connection.connectTree(share_name)
            handle = connection.openFile(tree, '\\', desiredAccess=mask,
                shareMode=FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                creationDisposition=FILE_OPEN, fileAttributes=0,
                creationOption=FILE_DIRECTORY_FILE)
            labels.append(label)
            evidence.append({'mask': mask, 'access': label})
        except Exception as exc:
            error = safe_error(exc)
            if error == 'access_denied':
                denied += 1
            else:
                errors.append(error)
        finally:
            if handle is not None:
                try: connection.closeFile(tree, handle)
                except Exception: pass
            if tree is not None:
                try: connection.disconnectTree(tree)
                except Exception: pass
        if label == 'WRITE' and label in labels:
            # Direct write access subsumes subdirectory/ACL/ownership alternatives.
            break
    return {'access': labels, 'write_status': 'allowed' if labels else 'unknown' if errors else 'denied',
            'write_method': 'root_access_open', 'write_evidence': evidence,
            'write_errors': sorted(set(errors))}


def probe(host, options, password, connection_factory=None, checkpoint=lambda _: None, clock=time.monotonic):
    if connection_factory is None:
        from impacket.smbconnection import SMBConnection
        connection_factory = SMBConnection
    started = datetime.now(timezone.utc).isoformat()
    result = {'host': host, 'observed_at': started, 'status': 'running', 'error': None,
              'server': {}, 'shares': [], 'entries': [], 'partial': False, 'limits': [],
              'coverage': 'files' if options['spider'] else 'shares'}
    deadline = clock() + 60
    connection = None
    last_checkpoint = clock()

    def check():
        if clock() >= deadline:
            raise TimeoutError()

    def save(force=False):
        nonlocal last_checkpoint
        if force or clock() - last_checkpoint >= 2:
            checkpoint(result)
            last_checkpoint = clock()

    try:
        connection = connection_factory(options.get('server_names', {}).get(host, host), host, sess_port=445, timeout=3)
        dialect = connection.getDialect()
        result['server']['dialect'] = {0x202: 'SMB 2.0.2', 0x210: 'SMB 2.1',
            0x300: 'SMB 3.0', 0x302: 'SMB 3.0.2', 0x311: 'SMB 3.1.1'}.get(dialect, 'SMB 1' if isinstance(dialect, str) else str(dialect))
        result['server'].update(signing_evidence(connection))
        result['server']['smb1_supported'] = None
        try:
            if options.get('credential_type') == 'kerberos':
                connection.kerberosLogin(options['username'], '', options['domain'], aesKey=password,
                                         kdcHost=options['kdc_host'], useCache=False)
            elif options.get('credential_type') == 'ntlm':
                pair = password.split(':')
                lmhash, nthash = (pair[0], pair[1]) if len(pair) == 2 else ('', pair[0])
                connection.login(options['username'], '', options['domain'], lmhash=lmhash, nthash=nthash, ntlmFallback=False)
            else:
                connection.login(options['username'], password, options['domain'], ntlmFallback=False)
        except Exception as exc:
            result.update(status='login_failed', error=safe_error(exc))
            return result
        finally:
            # NTLM challenge identity remains useful even when login is denied.
            for key, method in [('name', 'getServerName'), ('domain', 'getServerDomain'), ('os', 'getServerOS')]:
                try:
                    result['server'][key] = str(getattr(connection, method)() or '')[:256]
                except Exception:
                    pass
        result['authentication'] = 'guest' if connection.isGuestSession() else 'authenticated' if options['mode'] == 'credentials' else 'anonymous'
        result['server']['guest'] = result['authentication'] == 'guest'
        check()
        try:
            discovered = connection.listShares()
        except Exception as exc:
            result.update(status='shares_failed', error=safe_error(exc))
            return result
        for raw in discovered:
            if len(result['shares']) >= 1024:
                result['partial'] = True; result['limits'].append('shares'); break
            name = str(raw['shi1_netname']).rstrip('\x00')
            if not name or len(name) > 256 or any(c in name for c in '/\\:') or any(ord(c) < 32 for c in name):
                result['partial'] = True; continue
            kind = int(raw['shi1_type']) & 0xFFFF
            result['shares'].append({'name': name, 'files': 0, 'type': kind,
                'remark': str(raw['shi1_remark']).rstrip('\x00')[:512], 'listing': 'not_checked', 'error': None, 'read_status': 'not_checked',
                'access': [], 'write_status': 'not_checked'})
        save(True)
        # First enumerate access for every share, even those excluded from recursion.
        roots = {}
        for share in result['shares']:
            check()
            try:
                items = connection.listPath(share['name'], '*')
                roots[share['name']] = items
                share.update(listing='listed', read_status='allowed')
                share['access'].append('READ')
            except Exception as exc:
                error = safe_error(exc)
                share.update(listing='failed', error=error,
                             read_status='denied' if error == 'access_denied' else 'unknown')
            if share['type'] == 0:
                rights = write_access(connection, share['name'], check)
                share['access'].extend(rights.pop('access'))
                share.update(rights)
            else:
                share['write_status'] = 'not_applicable'
            save()
        save(True)
        stop = False
        for share in result['shares']:
            check()
            if not options['spider'] or share['type'] != 0 or share['read_status'] != 'allowed':
                continue
            if not options['include_admin'] and (share['name'].upper() == 'ADMIN$' or (len(share['name']) == 2 and share['name'][1] == '$')):
                share['walk_status'] = 'admin_skipped'; continue
            share['walk_status'] = 'running'
            queue = deque([('', 0, None)])
            while queue:
                check()
                parent, level, parent_entry = queue.popleft()
                try:
                    items = roots[share['name']] if not parent else connection.listPath(share['name'], parent.replace('/', '\\') + '\\*')
                except Exception as exc:
                    error = safe_error(exc)
                    result['partial'] = True
                    if parent_entry is not None:
                        parent_entry['metadata'].update(listing='failed', error=error)
                    else:
                        share.update(listing='failed', error=error)
                    continue
                if parent_entry is None:
                    share['listing'] = 'listed'
                else:
                    parent_entry['metadata']['listing'] = 'listed'
                if not options['spider']:
                    break
                for item in items:
                    name = item.get_longname()
                    if name in ('.', '..'):
                        continue
                    if len(result['entries']) >= options['max_entries']:
                        stop = True; result['partial'] = True; result['limits'].append('entries'); break
                    # Never follow reparse points (junctions/symlinks) out of the selected tree.
                    try:
                        if '/' in name or '\\' in name:
                            raise ValueError()
                        path = relative_path(f'{parent}/{name}' if parent else name)
                    except ValueError:
                        result['partial'] = True; continue
                    is_dir = bool(item.is_directory())
                    attributes = item.get_attributes()
                    entry = {'share': share['name'], 'path': path, 'parent': parent, 'name': name,
                             'kind': 'directory' if is_dir else 'file',
                             'metadata': {'size': f'{item.get_filesize()} B', 'ctime_epoch': stamp(item.get_ctime_epoch()),
                                          'mtime_epoch': stamp(item.get_mtime_epoch()), 'atime_epoch': stamp(item.get_atime_epoch()),
                                          'listing': 'not_checked' if is_dir else None,
                                          'reparse_point': bool(attributes & 0x400)}}
                    result['entries'].append(entry)
                    if is_dir:
                        if attributes & 0x400:
                            entry['metadata']['listing'] = 'reparse_skipped'
                        elif level >= options['depth']:
                            entry['metadata']['listing'] = 'depth_limit'
                            result['partial'] = True
                            if 'depth' not in result['limits']: result['limits'].append('depth')
                        else:
                            queue.append((path, level + 1, entry))
                    else:
                        share['files'] += 1
                save()
                if stop:
                    break
            share['walk_status'] = 'partial' if stop else 'completed'
            if stop:
                break
        result['coverage'] = 'files' if options['spider'] else 'shares'
        result['status'] = 'completed'
    except TimeoutError:
        result.update(status='partial', partial=True)
        result['limits'].append('time')
    except Exception as exc:
        result.update(status='failed', error=safe_error(exc), partial=bool(result['shares']))
    finally:
        save(True)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return result


def main():
    output = Path(sys.argv[1])
    payload = json.load(sys.stdin)
    def snapshot(data):
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(temporary, output)
    probe(payload['host'], payload['options'], payload.pop('password'), checkpoint=snapshot)


if __name__ == '__main__':
    main()
