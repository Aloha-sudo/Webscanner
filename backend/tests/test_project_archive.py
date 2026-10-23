import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
# Match the existing SQLite fixtures when production settings are unavailable.
import sys
from types import ModuleType, SimpleNamespace
try:
    import pydantic_settings
except ModuleNotFoundError:
    config = ModuleType('app.core.config')
    config.settings = SimpleNamespace(DATABASE_URL='postgresql://scanner:scanner@localhost/scanner')
    sys.modules.setdefault('app.core.config', config)
from app.core.db import Base
from app.models.scan import Project, NetworkPart, Scan, Host, Port, Service, Screenshot
from app.reports.project_archive import export_project, read_archive, import_project

class ProjectArchiveTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        p=Project(name='Original',name_key='original',description='Обследование LAN');self.db.add(p);self.db.flush()
        n=NetworkPart(project_id=p.id,name='LAN',name_key='lan');self.db.add(n);self.db.flush()
        s=Scan(project_id=p.id,network_part_id=n.id,project=p.name,network=n.name,target='192.0.2.1',status='completed',dns_status='completed',comment='Evidence',source_host='192.0.2.2');self.db.add(s);self.db.flush()
        h=Host(scan_id=s.id,ip='192.0.2.1',dns_result={'names':['host.test']});self.db.add(h);self.db.flush()
        port=Port(host_id=h.id,port=443,service='https');self.db.add(port);self.db.flush()
        self.db.add(Service(port_id=port.id,url='https://192.0.2.1',title='test'))
        self.db.add(Screenshot(scan_id=s.id,url='https://192.0.2.1',minio_path=f'local://scan_{s.id}/test.png'))
        self.db.commit();self.project=p;self.scan=s
        directory=self.root/str(s.id)/'screenshots';directory.mkdir(parents=True);(directory/'test.png').write_bytes(b'image')
        (self.root/str(s.id)/'original.xml').write_text('<nmaprun/>')
    def tearDown(self):
        self.db.close();self.engine.dispose();self.temp.cleanup()
    def archive(self):return export_project(self.db,self.project.id,self.root).getvalue()
    def test_roundtrip_remaps_data_files_and_screenshots(self):
        payload,files=read_archive(self.archive())
        new=import_project(self.db,payload,files,self.root,'Copy')
        s=self.db.query(Scan).filter_by(project_id=new).one()
        self.assertNotEqual(s.id,self.scan.id);self.assertEqual(s.comment,'Evidence')
        self.assertEqual(s.hosts[0].ports[0].service_obj.title,'test')
        self.assertEqual(s.hosts[0].dns_result,{'names':['host.test']})
        self.assertEqual(s.screenshots[0].minio_path,f'local://scan_{s.id}/test.png')
        self.assertEqual((self.root/str(s.id)/'screenshots/test.png').read_bytes(),b'image')
        self.assertEqual((self.root/str(s.id)/'original.xml').read_text(),'<nmaprun/>')
    def test_active_scan_and_dns_rejected(self):
        self.scan.status='running';self.db.commit()
        with self.assertRaises(ValueError):self.archive()
        self.scan.status='completed';self.scan.dns_status='queued';self.db.commit()
        with self.assertRaises(ValueError):self.archive()
    def test_collision_preserves_existing_project(self):
        payload,files=read_archive(self.archive())
        with self.assertRaises(ValueError):import_project(self.db,payload,files,self.root,'Original')
        self.assertEqual(self.db.query(Project).count(),1)
    def test_missing_screenshot_rolls_back_database_and_files(self):
        payload,files=read_archive(self.archive());del files[f'files/{self.scan.id}/screenshots/test.png']
        with self.assertRaises(ValueError):import_project(self.db,payload,files,self.root,'Copy')
        self.assertEqual(self.db.query(Project).count(),1)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),[str(self.scan.id)])
    def test_retry_link_remapped(self):
        second=Scan(project_id=self.project.id,network_part_id=self.scan.network_part_id,target='192.0.2.1',status='failed',retry_of_id=self.scan.id)
        self.db.add(second);self.db.commit()
        payload,files=read_archive(self.archive());new=import_project(self.db,payload,files,self.root,'Copy')
        scans=self.db.query(Scan).filter_by(project_id=new).order_by(Scan.id).all()
        self.assertEqual(scans[1].retry_of_id,scans[0].id)
    def test_corruption_traversal_and_duplicate_entries_rejected(self):
        data=self.archive()
        for name,value in [('project.json',b'{}'),('../outside',b'evil'),('project.json',b'{}')]:
            stream=io.BytesIO(data)
            with zipfile.ZipFile(stream,'a') as z:z.writestr(name,value)
            with self.assertRaises(ValueError):read_archive(stream.getvalue())
    def test_description_saved_map_and_part_dns_roundtrip(self):
        self.project.map_view={'report_ids':[self.scan.id], 'source':self.scan.id, 'network_part_id':self.scan.network_part_id, 'whole_project':True,'merge_parts':False}
        self.db.get(NetworkPart,self.scan.network_part_id).dns_defaults={'server':'192.0.2.53'}
        self.db.commit()
        payload,files=read_archive(self.archive());new=import_project(self.db,payload,files,self.root,'Copy')
        project=self.db.get(Project,new);scan=self.db.query(Scan).filter_by(project_id=new).one()
        self.assertEqual(project.description,'Обследование LAN')
        self.assertEqual(project.map_view['report_ids'],[scan.id]);self.assertEqual(project.map_view['source'],scan.id)
        self.assertEqual(project.map_view['network_part_id'],scan.network_part_id)
        self.assertFalse(project.map_view['merge_parts'])
        self.assertEqual(self.db.get(NetworkPart,scan.network_part_id).dns_defaults,{'server':'192.0.2.53'})
    def test_checksum_mismatch_rejected_without_duplicate_names(self):
        output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.archive())) as source, zipfile.ZipFile(output,'w') as target:
            for item in source.infolist():target.writestr(item.filename,b'{}' if item.filename=='project.json' else source.read(item.filename))
        with self.assertRaisesRegex(ValueError,'Контрольные суммы'):read_archive(output.getvalue())
    def test_invalid_foreign_key_and_active_import_rejected(self):
        payload,files=read_archive(self.archive())
        payload['hosts'][0]['scan_id']=999
        import hashlib
        files['project.json']=json.dumps(payload).encode()
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as target:
            for name,content in files.items():target.writestr(name,content)
            target.writestr('manifest.json',json.dumps({'format':'webscanner-project','version':1,'sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}))
        with self.assertRaisesRegex(ValueError,'связи'):read_archive(output.getvalue())
    def test_symlink_export_rejected(self):
        (self.root/str(self.scan.id)/'link').symlink_to('/etc/hosts')
        with self.assertRaises(ValueError):self.archive()
