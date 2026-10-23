import unittest
from types import SimpleNamespace
from sqlalchemy import create_engine, text, Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import Session, declarative_base
from app.core.catalog import clean_name,name_key,resolve_context
from app.core.migrations import migrate
from app.schemas.scan import TeamMetadata
Base=declarative_base()
class Project(Base):
    __tablename__='projects_test'
    id=Column(Integer,primary_key=True)
    name=Column(String)
    name_key=Column(String,unique=True)
class Part(Base):
    __tablename__='parts_test'
    id=Column(Integer,primary_key=True)
    project_id=Column(Integer)
    name=Column(String)
    name_key=Column(String)
class CatalogTests(unittest.TestCase):
    def test_normalized_names_preserve_display(self):
        self.assertEqual(clean_name('  Офис   компании  '),'Офис компании')
        self.assertEqual(name_key('ОФИС   Компании'),name_key('офис компании'))
        with self.assertRaises(ValueError):clean_name(' ')
    def test_existing_ids_are_canonical_and_cross_project_is_rejected(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([Project(id=1,name='Компания',name_key='компания'),Project(id=2,name='Другая',name_key='другая'),Part(id=10,project_id=1,name='Офис',name_key='офис')]);db.commit()
            value=resolve_context(db,TeamMetadata(project_id=1,network_part_id=10,project='Опечатка'),Project,Part)
            self.assertEqual(value['project'],'Компания')
            self.assertEqual(value['network'],'Офис')
            with self.assertRaises(ValueError):resolve_context(db,TeamMetadata(project_id=2,network_part_id=10),Project,Part)
            with self.assertRaises(ValueError):resolve_context(db,TeamMetadata(project='Несуществующий',network='Офис'),Project,Part)
            self.assertIsNone(resolve_context(db,TeamMetadata(),Project,Part)['project_id'])
    def test_legacy_migration_preserves_reports_and_merges_only_case_whitespace(self):
        engine=create_engine('sqlite://')
        with engine.begin() as c:
            c.execute(text('CREATE TABLE scans (id INTEGER PRIMARY KEY,project TEXT,network TEXT,target TEXT)'))
            c.execute(text('CREATE TABLE ports (id INTEGER PRIMARY KEY)'))
            c.execute(text("INSERT INTO scans VALUES (1,' Компания ','Офис','10.0.0.1'),(2,'КОМПАНИЯ',' офис ','10.0.0.2'),(3,'Компания','Офиc','10.0.0.3')"))
        migrate(engine);migrate(engine)
        with engine.connect() as c:
            rows=c.execute(text('SELECT id,project_id,network_part_id,target FROM scans ORDER BY id')).all()
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[0].project_id,rows[1].project_id)
            self.assertEqual(rows[0].network_part_id,rows[1].network_part_id)
            self.assertNotEqual(rows[0].network_part_id,rows[2].network_part_id)
            self.assertEqual(rows[2].target,'10.0.0.3')
            self.assertEqual(c.execute(text('SELECT count(*) FROM projects')).scalar(),1)
            self.assertEqual(c.execute(text('SELECT count(*) FROM network_parts')).scalar(),2)
