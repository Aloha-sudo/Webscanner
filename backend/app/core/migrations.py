"""Versioned migrations for existing installations. No data is deleted."""
from sqlalchemy import text, inspect


def migrate(engine):
    with engine.begin() as conn:
        if conn.dialect.name == 'postgresql':
            conn.execute(text("SELECT pg_advisory_xact_lock(743219)") )
        conn.execute(text('CREATE TABLE IF NOT EXISTS scanner_schema_version (version INTEGER PRIMARY KEY)'))
        versions = set(conn.execute(text('SELECT version FROM scanner_schema_version')).scalars())
        if 1 not in versions:
            columns = {c['name'] for c in inspect(conn).get_columns('scans')}
            additions = {'scan_type': "VARCHAR(50) DEFAULT 'quick'", 'ports': 'VARCHAR(500)',
                         'comment': 'TEXT', 'speed': "VARCHAR(20) DEFAULT 'normal'"}
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE scans ADD COLUMN {name} {definition}'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (1)'))
        if 2 not in versions:
            columns = {c['name'] for c in inspect(conn).get_columns('ports')}
            if 'banner' not in columns:
                conn.execute(text('ALTER TABLE ports ADD COLUMN banner TEXT'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (2)'))
        if 3 not in versions:
            columns = {c['name'] for c in inspect(conn).get_columns('scans')}
            for name in ('exclude_ips', 'exclude_hosts', 'exclude_ports'):
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE scans ADD COLUMN {name} TEXT'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (3)'))
        if 4 not in versions:
            columns = {c['name'] for c in inspect(conn).get_columns('scans')}
            additions = {'project':'VARCHAR(120)', 'network':'VARCHAR(120)', 'source_host':'VARCHAR(253)', 'author':'VARCHAR(120)', 'observed_at':'TIMESTAMP WITH TIME ZONE' if conn.dialect.name == 'postgresql' else 'DATETIME', 'scope_targets':'TEXT','scope_ports':'TEXT','scope_confirmed':'BOOLEAN DEFAULT FALSE'}
            for name, definition in additions.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE scans ADD COLUMN {name} {definition}'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (4)'))
        if 5 not in versions:
            from sqlalchemy import Table, MetaData, select, insert, update
            from app.core.catalog import clean_name, name_key
            columns = {c['name'] for c in inspect(conn).get_columns('scans')}
            for name, target in (('project_id','projects'),('network_part_id','network_parts')):
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE scans ADD COLUMN {name} INTEGER REFERENCES {target}(id)'))
            metadata=MetaData()
            # Also supports older databases initialized without ORM tables.
            conn.execute(text('CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, name_key VARCHAR(240) UNIQUE NOT NULL)') if conn.dialect.name == 'sqlite' else text('CREATE TABLE IF NOT EXISTS projects (id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL, name_key VARCHAR(240) UNIQUE NOT NULL)'))
            conn.execute(text('CREATE TABLE IF NOT EXISTS network_parts (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), name VARCHAR(120) NOT NULL, name_key VARCHAR(240) NOT NULL, UNIQUE(project_id,name_key))') if conn.dialect.name == 'sqlite' else text('CREATE TABLE IF NOT EXISTS network_parts (id SERIAL PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), name VARCHAR(120) NOT NULL, name_key VARCHAR(240) NOT NULL, UNIQUE(project_id,name_key))'))
            projects=Table('projects',metadata,autoload_with=conn)
            parts=Table('network_parts',metadata,autoload_with=conn)
            scan_columns={c['name'] for c in inspect(conn).get_columns('scans')}
            if 'project' in scan_columns and 'network' in scan_columns:
                for row in conn.execute(text('SELECT id,project,network FROM scans WHERE project IS NOT NULL')).all():
                    if not row.project.strip():
                        continue
                    pname=clean_name(row.project)
                    pid=conn.execute(select(projects.c.id).where(projects.c.name_key==name_key(pname))).scalar()
                    if pid is None:
                        pid=conn.execute(insert(projects).values(name=pname,name_key=name_key(pname))).inserted_primary_key[0]
                    partname=clean_name(row.network) if row.network and row.network.strip() else 'Без части сети'
                    nid=conn.execute(select(parts.c.id).where(parts.c.project_id==pid,parts.c.name_key==name_key(partname))).scalar()
                    if nid is None:
                        nid=conn.execute(insert(parts).values(project_id=pid,name=partname,name_key=name_key(partname))).inserted_primary_key[0]
                    conn.execute(text('UPDATE scans SET project_id=:pid,network_part_id=:nid,project=:p,network=:n WHERE id=:id'),{'pid':pid,'nid':nid,'p':conn.execute(select(projects.c.name).where(projects.c.id==pid)).scalar(),'n':conn.execute(select(parts.c.name).where(parts.c.id==nid)).scalar(),'id':row.id})
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_scans_project_id ON scans(project_id)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_scans_network_part_id ON scans(network_part_id)'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (5)'))
        # Version 6 belonged to the reverted dashboard experiment. Never reuse it.
        if 7 not in versions:
            columns = {c['name'] for c in inspect(conn).get_columns('scans')}
            if 'retry_of_id' not in columns:
                conn.execute(text('ALTER TABLE scans ADD COLUMN retry_of_id INTEGER'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_scans_retry_of_id ON scans(retry_of_id)'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (7)'))

        if 8 not in versions:
            additions = {
                'scans': {'dns_options': 'JSON', 'dns_status': "VARCHAR(30) DEFAULT 'not_requested'", 'dns_summary': 'JSON', 'dns_job_id': 'VARCHAR(40)'},
                'hosts': {'dns_result': 'JSON'},
                'network_parts': {'dns_defaults': 'JSON'},
            }
            for table, fields in additions.items():
                if not inspect(conn).has_table(table):
                    continue
                columns = {c['name'] for c in inspect(conn).get_columns(table)}
                for name, definition in fields.items():
                    if name not in columns:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (8)'))

        if 9 not in versions:
            if inspect(conn).has_table('projects'):
                columns = {c['name'] for c in inspect(conn).get_columns('projects')}
                for name, definition in {'description': 'TEXT', 'map_view': 'JSON'}.items():
                    if name not in columns:
                        conn.execute(text(f'ALTER TABLE projects ADD COLUMN {name} {definition}'))
            conn.execute(text('INSERT INTO scanner_schema_version (version) VALUES (9)'))
