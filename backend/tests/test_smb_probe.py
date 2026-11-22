import unittest
from app.core.smb_probe import probe
from app.schemas.smb import SmbStart, targets


class Denied(Exception):
    def getErrorCode(self): return 0xC0000022


class Item:
    def __init__(self, name, directory=False, attributes=0):
        self.name, self.directory, self.attributes = name, directory, attributes
    def get_longname(self): return self.name
    def is_directory(self): return self.directory
    def get_attributes(self): return self.attributes
    def get_filesize(self): return 12
    def get_ctime_epoch(self): return 1700000000
    get_mtime_epoch = get_ctime_epoch
    get_atime_epoch = get_ctime_epoch


class Connection:
    def __init__(self, *args, **kwargs):
        self.login_args = None; self.paths = []; self.closed = False
    def getSMBServer(self):
        from types import SimpleNamespace
        return SimpleNamespace(_Connection={'ServerSecurityMode':3})
    def getDialect(self): return 0x311
    def isSigningRequired(self): return True
    def login(self, username, password, domain, **kwargs): self.login_args = (username,password,domain)
    def isGuestSession(self): return False
    def getServerName(self): return 'FS01'
    def getServerDomain(self): return 'LAB'
    def getServerOS(self): return 'Windows'
    def listShares(self):
        return [{'shi1_netname': name+'\x00', 'shi1_type': kind, 'shi1_remark': 'Test\x00'}
                for name,kind in [('Docs',0),('Private',0),('C$',0),('IPC$',3)]]
    def listPath(self, share, path):
        self.paths.append((share,path))
        if share == 'Private' or path == 'Denied\\*': raise Denied('must not be retained')
        if path == '*': return [Item('folder',True),Item('empty',True),Item('Denied',True),Item('junction',True,0x400),Item('a.txt'),Item('..'),Item('../unsafe')]
        if path == 'folder\\*': return [Item('b.txt')]
        return []
    def connectTree(self, share): return share
    def disconnectTree(self, tree): pass
    def openFile(self, tree, path, **kwargs):
        if tree != 'Docs': raise Denied()
        return 1
    def closeFile(self, tree, handle): pass
    def close(self): self.closed = True


class SmbProbeTests(unittest.TestCase):
    def options(self, **kwargs):
        return SmbStart(targets='192.0.2.1', **{'spider':True, **kwargs}).public()

    def run_probe(self, options, client=None):
        client = client or Connection()
        report = probe('192.0.2.1', options, 'password', connection_factory=lambda *a,**kw: client)
        self.assertTrue(client.closed)
        return report, client

    def test_walk_lists_all_shares_and_empty_denied_and_reparse_folders(self):
        report,client = self.run_probe(self.options())
        self.assertEqual(report['status'],'completed')
        self.assertEqual([s['name'] for s in report['shares']],['Docs','Private','C$','IPC$'])
        self.assertEqual(report['shares'][0]['listing'],'listed')
        self.assertEqual(report['shares'][1]['error'],'access_denied')
        self.assertEqual(report['shares'][2]['walk_status'],'admin_skipped')
        entries = {e['path']:e for e in report['entries']}
        self.assertEqual(entries['empty']['metadata']['listing'],'listed')
        self.assertEqual(entries['Denied']['metadata']['error'],'access_denied')
        self.assertEqual(entries['junction']['metadata']['listing'],'reparse_skipped')
        self.assertNotIn(('Docs','junction\\*'),client.paths)
        self.assertIn('folder/b.txt',entries)
        self.assertEqual(report['server']['dialect'],'SMB 3.1.1')
        self.assertTrue(report['server']['signing_required'])
        self.assertNotIn('password',str(report))

    def test_listing_only_admin_opt_in_depth_and_entry_limits(self):
        report,client = self.run_probe(self.options(spider=False))
        self.assertEqual(report['entries'],[])
        self.assertIn(('Docs','*'),client.paths)
        report,client = self.run_probe(self.options(depth=0,include_admin=True))
        self.assertIn(('C$','*'),client.paths)
        self.assertNotIn(('Docs','folder\\*'),client.paths)
        self.assertTrue(report['partial'])
        report,client = self.run_probe(self.options(max_entries=1))
        self.assertEqual(len(report['entries']),1)
        self.assertIn('entries',report['limits'])

    def test_login_failure_retains_no_exception_text_or_credentials(self):
        client = Connection()
        class BadLogin(Exception):
            def getErrorCode(self): return 0xC000006D
        def login(*args,**kwargs): raise BadLogin('PASSWORD=password')
        client.login = login
        report,_ = self.run_probe(self.options(mode='credentials',username='user'),client)
        self.assertEqual(report['status'],'login_failed')
        self.assertEqual(report['error'],'authentication_failed')
        self.assertEqual(client.paths,[])
        self.assertNotIn('password',str(report))

    def test_options_and_address_bounds(self):
        value = SmbStart(targets='192.0.2.1', mode='credentials', username='LAB\\user',password='secret')
        self.assertEqual(value.domain,'LAB')
        self.assertEqual(value.username,'user')
        self.assertNotIn('password',value.public())
        self.assertNotIn('secret',str(value))
        self.assertEqual(len(targets('192.0.2.0/24')),254)
        for value in ('192.0.0.0/16','host.example','0.0.0.0','224.0.0.1'):
            with self.assertRaises(ValueError): targets(value)
        self.assertEqual(SmbStart(targets='192.0.2.1',username='ignored',password='ignored').public()['username'],'')

    def test_nt_hash_and_lm_nt_authentication_do_not_use_password(self):
        for credential in ('1' * 32, '2' * 32 + ':' + '1' * 32):
            options = SmbStart(targets='192.0.2.1', mode='credentials', username='user',
                               credential_type='ntlm', nt_hash=credential, password='ignored')
            self.assertEqual(options.password.get_secret_value(), '')
            self.assertNotIn('nt_hash', options.public())
            self.assertNotIn(credential, str(options))
            client = Connection(); calls = []
            client.login = lambda *args, **kwargs: calls.append((args,kwargs))
            report = probe('192.0.2.1', options.public(), credential,
                           connection_factory=lambda *args,**kwargs: client)
            self.assertEqual(calls[0][0][1], '')
            self.assertEqual(calls[0][1]['nthash'], '1' * 32)
            self.assertEqual(calls[0][1]['lmhash'], '2' * 32 if ':' in credential else '')
            self.assertNotIn(credential, str(report))
        for value in ('not-a-hash', 'a' * 31, 'z' * 32, 'a' * 64):
            with self.assertRaises(ValueError):
                SmbStart(targets='192.0.2.1', mode='credentials', username='user',
                         credential_type='ntlm', nt_hash=value)

    def test_kerberos_aes128_and_aes256_use_kdc_and_spn_without_ntlm_fallback(self):
        for key in ('a' * 32, 'b' * 64):
            options = SmbStart(targets='192.0.2.1', mode='credentials', username='reader', domain='lab.example',
                credential_type='kerberos', aes_key=key, kdc_host='192.0.2.10', server_names={'192.0.2.1':'fs01.lab.example'})
            self.assertEqual(options.credential(), key)
            self.assertNotIn(key, str(options))
            self.assertNotIn('aes_key', options.public())
            client = Connection(); calls = []; connections = []
            client.kerberosLogin = lambda *args,**kwargs: calls.append((args,kwargs))
            def factory(*args,**kwargs):
                connections.append(args); return client
            report = probe('192.0.2.1', options.public(), key, connection_factory=factory)
            self.assertEqual(connections, [('fs01.lab.example','192.0.2.1')])
            self.assertEqual(calls[0][0], ('reader','','lab.example'))
            self.assertEqual(calls[0][1], {'aesKey':key,'kdcHost':'192.0.2.10','useCache':False})
            self.assertIsNone(client.login_args, 'no NTLM fallback')
            self.assertNotIn(key, str(report))
        for override in ({'aes_key':'invalid'}, {'server_names':{}}, {'server_names':{'192.0.2.1':'192.0.2.1'}}, {'kdc_host':''}):
            values = dict(targets='192.0.2.1',mode='credentials',username='reader',domain='lab.example',
                credential_type='kerberos',aes_key='a'*32,kdc_host='192.0.2.10',server_names={'192.0.2.1':'fs01.lab.example'})
            with self.assertRaises(ValueError): SmbStart(**{**values,**override})

    def test_smb311_server_signing_is_not_the_client_forced_signing_policy(self):
        from types import SimpleNamespace
        client = Connection()
        client.getSMBServer = lambda: SimpleNamespace(_Connection={'ServerSecurityMode':1})
        report,_ = self.run_probe(self.options(spider=False),client)
        self.assertFalse(report['server']['signing_required'])
        self.assertTrue(report['server']['client_signing_required'])
        self.assertEqual(report['server']['signing_source'],'server_security_mode')
        self.assertEqual(report['coverage'],'shares')
        self.assertEqual(report['entries'],[])
        # Administrative-share access is checked even when disk recursion is disabled.
        self.assertIn(('C$','*'),client.paths)
        self.assertIn('READ',report['shares'][2]['access'])
        self.assertIn('WRITE',report['shares'][0]['access'])
        self.assertEqual(report['shares'][0]['write_method'],'root_access_open')
        self.assertIn('READ',report['shares'][3]['access'])
        self.assertEqual(report['shares'][3]['write_status'],'not_applicable')

    def test_root_access_check_never_creates_files_and_preserves_unknown_errors(self):
        from app.core.smb_probe import write_access
        from impacket.smb3structs import FILE_OPEN, FILE_DIRECTORY_FILE
        client = Connection(); opened = []; closed = []; disconnected = []
        def opened_root(tree,path,**kwargs):
            opened.append((path,kwargs)); return 0
        client.openFile = opened_root
        client.closeFile = lambda tree,handle: closed.append(handle)
        client.disconnectTree = lambda tree: disconnected.append(tree)
        rights = write_access(client,'Docs')
        self.assertEqual(rights['access'],['WRITE'])
        self.assertEqual(opened[0][0],'\\')
        self.assertEqual(opened[0][1]['creationDisposition'],FILE_OPEN)
        self.assertEqual(opened[0][1]['creationOption'],FILE_DIRECTORY_FILE)
        self.assertEqual(closed,[0]);self.assertEqual(disconnected,['Docs'])
        def unknown(*args,**kwargs): raise OSError('sensitive exception text')
        client.openFile = unknown
        rights = write_access(client,'Docs')
        self.assertEqual(rights['access'],[])
        self.assertEqual(rights['write_status'],'unknown')
        self.assertNotIn('sensitive',str(rights))

    def test_default_is_shares_only_and_depth_limit_is_explained(self):
        self.assertFalse(SmbStart(targets='192.0.2.1').spider)
        report,_ = self.run_probe(self.options(depth=0))
        self.assertIn('depth',report['limits'])
