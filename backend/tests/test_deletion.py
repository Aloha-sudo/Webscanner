import unittest
from types import SimpleNamespace
from app.reports.deletion import validate_project_deletion
class DeletionTests(unittest.TestCase):
    def test_completed_and_failed_reports_can_be_deleted(self):
        scans=[SimpleNamespace(id=1,status='completed'),SimpleNamespace(id=2,status='failed')]
        self.assertEqual(validate_project_deletion(scans,2),[1,2])
    def test_active_report_blocks_entire_project(self):
        with self.assertRaisesRegex(ValueError,'активные'):
            validate_project_deletion([SimpleNamespace(id=1,status='running')],1)
    def test_changed_project_requires_new_confirmation(self):
        with self.assertRaisesRegex(ValueError,'изменился'):
            validate_project_deletion([SimpleNamespace(id=1,status='completed')],2)
    def test_empty_project_is_not_deleted(self):
        with self.assertRaises(ValueError):validate_project_deletion([],1)

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, event
from sqlalchemy.orm import Session, declarative_base
from app.reports.deletion import remove_project_records
Base=declarative_base()
class Project(Base):
    __tablename__='projects'
    id=Column(Integer,primary_key=True)
class Part(Base):
    __tablename__='parts'
    id=Column(Integer,primary_key=True)
    project_id=Column(Integer,ForeignKey('projects.id'))
class Scan(Base):
    __tablename__='scans'
    id=Column(Integer,primary_key=True)
    project_id=Column(Integer,ForeignKey('projects.id'))
    network_part_id=Column(Integer,ForeignKey('parts.id'))
    project=Column(String)
    network=Column(String)
    status=Column(String)
    source_host=Column(String)
    target=Column(String)
class ProjectRemovalTests(unittest.TestCase):
    def run_case(self,delete_reports):
        engine=create_engine('sqlite://')
        @event.listens_for(engine,'connect')
        def enable_foreign_keys(conn,record):conn.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                project=Project(id=1);db.add(project);db.flush()
                db.add(Part(id=2,project_id=1));db.flush()
                db.add(Scan(id=3,project_id=1,network_part_id=2,project='Client',network='Office',status='completed',source_host='point1',target='10.0.0.1'))
                db.commit()
                self.assertEqual(remove_project_records(db,project,Part,Scan,1,delete_reports),[3])
                self.assertIsNone(db.get(Project,1));self.assertIsNone(db.get(Part,2))
                scan=db.get(Scan,3)
                if delete_reports:self.assertIsNone(scan)
                else:
                    self.assertIsNotNone(scan)
                    self.assertIsNone(scan.project_id);self.assertIsNone(scan.network_part_id)
                    self.assertIsNone(scan.project);self.assertIsNone(scan.network)
                    self.assertEqual(scan.status,'completed');self.assertEqual(scan.source_host,'point1');self.assertEqual(scan.target,'10.0.0.1')
        finally:engine.dispose()
    def test_default_preserves_results_and_detaches_before_deleting_parts(self):self.run_case(False)
    def test_explicit_full_deletion_removes_scan(self):self.run_case(True)
