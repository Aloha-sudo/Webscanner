import io
import tempfile
from pathlib import Path
import unittest
import zipfile
from app.core.smb_file_ops import operate,permissions,preview,checked_path,FileLimit,MAX_DOWNLOAD
from app.schemas.smb import SmbAction


class Denied(Exception):
    def getErrorCode(self):return 0xC0000022


class Entry:
    def __init__(self,name,directory=False,reparse=False):self.name,self.directory,self.reparse=name,directory,reparse
    def get_longname(self):return self.name
    def get_attributes(self):return 0x400 if self.reparse else 0
    def is_directory(self):return self.directory
    def get_filesize(self):return 6
    def get_mtime_epoch(self):return 1700000000
    get_ctime_epoch=get_mtime_epoch
    get_atime_epoch=get_mtime_epoch


class Client:
    def __init__(self):self.opened=[];self.closed=[];self.content=b'hello!';self.reads=[];self.disconnects=[]
    def listPath(self,share,path):
        if path=='*':return [Entry('folder',True),Entry('hello.txt'),Entry('secret.txt'),Entry('link',True,True)]
        if path=='folder':return [Entry('folder',True)]
        if path=='hello.txt':return [Entry('hello.txt')]
        if path=='link':return [Entry('link',True,True)]
        if path=='folder\\*':return [Entry('inside.txt')]
        return []
    def connectTree(self,share):return 0
    def disconnectTree(self,tree):self.disconnects.append(tree)
    def openFile(self,tree,path,**kwargs):self.opened.append((path,kwargs));return 0
    def closeFile(self,tree,handle):self.closed.append(handle)
    def queryInfo(self,tree,handle):return {'EndOfFile':len(self.content)}
    def readFile(self,tree,handle,offset,bytesToRead):self.reads.append((offset,bytesToRead));return self.content[offset:offset+bytesToRead]


class SmbFileOpsTests(unittest.TestCase):
    def test_live_listing_and_subfolder_do_not_require_a_spider(self):
        conn=Client()
        page=operate(conn,'Docs','','list',{'query':'','offset':0},Path('/unused'))
        self.assertEqual(page['total'],4)
        self.assertTrue(page['live'])
        self.assertEqual(page['items'][0]['kind'],'directory')
        page=operate(conn,'Docs','folder','list',{},Path('/unused'))
        self.assertEqual(page['items'][0]['path'],'folder/inside.txt')
        page=operate(conn,'Docs','','list',{'query':'HELLO'},Path('/unused'))
        self.assertEqual(page['total'],1)

    def test_download_and_preview_use_only_existing_read_handles(self):
        from impacket.smb3structs import FILE_OPEN,FILE_OPEN_REPARSE_POINT
        conn=Client()
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'file'
            result=operate(conn,'Docs','hello.txt','preview',{},output)
            self.assertEqual(output.read_bytes(),b'hello!')
            self.assertEqual(result['preview']['text'],'hello!')
            self.assertEqual(conn.opened[0][1]['creationDisposition'],FILE_OPEN)
            self.assertTrue(conn.opened[0][1]['creationOption']&FILE_OPEN_REPARSE_POINT)
            self.assertEqual(conn.closed,[0]);self.assertEqual(conn.disconnects,[0])
            self.assertEqual(conn.reads,[(0,6)])

    def test_file_size_and_reparse_limits(self):
        conn=Client()
        conn.queryInfo=lambda *args:{'EndOfFile':MAX_DOWNLOAD+1}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileLimit):operate(conn,'Docs','hello.txt','download',{},Path(directory)/'out')
        self.assertEqual(conn.reads,[])
        for path in ('link','link/anything.txt'):
            with self.assertRaisesRegex(ValueError,'reparse_blocked'):operate(Client(),'Docs',path,'list',{},Path('/unused'))
        for path in ('../file','/file','C:/file','folder//file','folder/*','\\\\server\\share'):
            with self.assertRaises(ValueError):checked_path(path)
        with self.assertRaises(ValueError):SmbAction(action='download',share='Docs',path='')

    def test_effective_file_rights_are_not_share_rights_and_do_not_modify_files(self):
        from impacket.smb3structs import FILE_READ_DATA,FILE_OPEN
        conn=Client()
        def opened(tree,path,**kwargs):
            self.assertEqual(kwargs['creationDisposition'],FILE_OPEN)
            if kwargs['desiredAccess']!=FILE_READ_DATA:raise Denied()
            return 0
        conn.openFile=opened
        result=permissions(conn,'Docs','hello.txt')
        self.assertEqual(result['rights'][0],{'right':'READ','status':'allowed'})
        self.assertTrue(all(r['status']=='denied' for r in result['rights'][1:]))
        self.assertEqual(conn.reads,[])

    def test_putty_and_public_keys_are_previewed_as_text(self):
        for name in ('fictional.ppk','id_ed25519.pub'):
            value=preview(b'FICTIONAL_KEY_FIXTURE',name)
            self.assertTrue(value['supported']);self.assertEqual(value['text'],'FICTIONAL_KEY_FIXTURE')

    def test_text_and_office_preview_is_bounded_and_never_executes_html(self):
        value=preview(b'<script>alert(1)</script>','test.html')
        self.assertEqual(value['text'],'<script>alert(1)</script>')
        self.assertFalse(preview(b'%PDF-binary','test.pdf')['supported'])
        def zipped(name,data):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as archive:archive.writestr(name,data)
            return buffer.getvalue()
        xml=b'<w:document xmlns:w="urn:word"><w:p><w:r><w:t>Example document</w:t></w:r></w:p></w:document>'
        self.assertIn('Example document',preview(zipped('word/document.xml',xml),'test.docx')['text'])
        self.assertFalse(preview(zipped('word/document.xml',b'<!DOCTYPE x><x/>'),'test.docx')['supported'])
        self.assertTrue(preview(b'a'*100000,'big.txt')['truncated'])
