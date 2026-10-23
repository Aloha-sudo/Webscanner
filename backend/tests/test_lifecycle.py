import enum
import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, Session
from app.core.scan_lifecycle import expire_overdue_scans
Base = declarative_base()
class Status:
    RUNNING='running'
    FAILED='failed'
class Scan(Base):
    __tablename__='test_scans'
    id=Column(Integer,primary_key=True)
    status=Column(String)
    stage=Column(String)
    started_at=Column(DateTime)
    finished_at=Column(DateTime)
    error_message=Column(String)
class LifecycleTests(unittest.TestCase):
    def test_only_expired_running_scans_are_failed(self):
        engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
        with Session(engine) as db:
            now=datetime.now(timezone.utc)
            for id,status,seconds in ((1,'running',3800),(2,'running',30),(3,'cancelled',3800),(4,'completed',3800)):
                db.add(Scan(id=id,status=status,started_at=now-timedelta(seconds=seconds)))
            db.commit(); expire_overdue_scans(db,Scan,Status)
            self.assertEqual([db.get(Scan,i).status for i in (1,2,3,4)],['failed','running','cancelled','completed'])
            self.assertIsNotNone(db.get(Scan,1).finished_at)
            self.assertTrue(db.get(Scan,1).error_message)
