import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
from types import SimpleNamespace
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock
import subprocess
from test_smb_jobs import load_functions


class Store:
    def __init__(self):self.data={}
    def get(self,key):return self.data.get(key)
    def getdel(self,key):return self.data.pop(key,None)
    def set(self,key,value,ex=None):self.data[key]=value
    def exists(self,key):return key in self.data
    def delete(self,key):self.data.pop(key,None)


class SmbActionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store();self.calls=[]
        self.token='a'*32;self.session='b'*32
        self.ns=load_functions('app/core/smb_actions.py',dict(Path=Path,re=re,json=json,shutil=shutil,
            time=time,sys=sys,os=os,signal=signal,settings=SimpleNamespace(SCANS_DIR=self.temp.name),
            secret_store=lambda:self.store,SESSION_TTL=900,ACTION_TTL=600))
        outer=self
        class Input(io.StringIO):
            def close(self):
                if self.closed:return
                if not self.getvalue():
                    super().close();return
                payload=json.loads(self.getvalue());outer.calls.append(payload)
                outer.directory.joinpath('download.bin').write_bytes(b'example')
                outer.directory.joinpath('result.json').write_text(json.dumps({'status':'completed','result':{'filename':'hello.txt','size':7}}))
                super().close()
        class Process:
            returncode=0
            stdin=Input()
            def poll(self):return 0
            def wait(self):return 0
        def popen(command,**kwargs):
            self.assertNotIn('private-secret',str(command));self.command=command;self.directory=Path(command[-1]);return Process()
        self.ns['subprocess']=SimpleNamespace(Popen=popen,PIPE=subprocess.PIPE,DEVNULL=subprocess.DEVNULL)
        self.store.set(self.ns['session_key'](self.session),json.dumps({'scan_id':1,'report_id':None,'hosts':['192.0.2.1'],'options':{},'secret':'private-secret'}))
        self.store.set(self.ns['action_key'](self.token),json.dumps({'id':self.token,'scan_id':1,'report_id':'report','session':self.session,'action':'download','status':'queued'}))
        self.store.set(self.ns['request_key'](self.token),json.dumps({'session':self.session,'host':'192.0.2.1','action':'download','share':'Docs','path':'hello.txt'}))

    def tearDown(self):self.temp.cleanup()

    def test_download_keeps_only_artifact_and_status_not_credentials(self):
        self.ns['run_action'](1,self.token)
        state=self.store.get(self.ns['action_key'](self.token))
        self.assertEqual(json.loads(state)['status'],'completed')
        self.assertNotIn('private-secret',state)
        self.assertEqual((Path(self.temp.name)/'.smb-actions'/self.token/'download.bin').read_bytes(),b'example')
        self.ns['run_action'](1,self.token)
        self.assertEqual(len(self.calls),1)

    def test_expired_session_never_spawns_network_process(self):
        self.store.delete(self.ns['session_key'](self.session))
        self.ns['run_action'](1,self.token)
        self.assertEqual(self.calls,[])
        self.assertEqual(json.loads(self.store.get(self.ns['action_key'](self.token)))['error'],'session_expired')

    def test_out_of_scope_host_never_spawns_network_process(self):
        request=json.loads(self.store.get(self.ns['request_key'](self.token)));request['host']='192.0.2.99'
        self.store.set(self.ns['request_key'](self.token),json.dumps(request))
        self.ns['run_action'](1,self.token)
        self.assertEqual(self.calls,[])

    def test_ftp_action_uses_generic_child_with_scoped_stdin(self):
        state=json.loads(self.store.get(self.ns['action_key'](self.token)));state['source']='ftp'
        self.store.set(self.ns['action_key'](self.token),json.dumps(state))
        session=json.loads(self.store.get(self.ns['session_key'](self.session)));session['options']={'source':'ftp','targets':['ftp://192.0.2.1:2121/docs']};session['hosts']=['ftp://192.0.2.1:2121/docs']
        self.store.set(self.ns['session_key'](self.session),json.dumps(session))
        request=json.loads(self.store.get(self.ns['request_key'](self.token)));request['location']='ftp://192.0.2.1:2121/docs/hello.txt'
        self.store.set(self.ns['request_key'](self.token),json.dumps(request))
        self.ns['run_action'](1,self.token)
        self.assertEqual(self.command[2],'app.core.secret_file_ops');self.assertEqual(self.calls[0]['secret'],'private-secret')
        self.assertEqual(json.loads(self.store.get(self.ns['action_key'](self.token)))['status'],'completed')

    def test_ftp_action_rechecks_remote_folder_scope_before_spawning(self):
        state=json.loads(self.store.get(self.ns['action_key'](self.token)));state['source']='ftp'
        self.store.set(self.ns['action_key'](self.token),json.dumps(state))
        session=json.loads(self.store.get(self.ns['session_key'](self.session)));session['options']={'source':'ftp','targets':['ftp://192.0.2.1/docs']}
        self.store.set(self.ns['session_key'](self.session),json.dumps(session))
        request=json.loads(self.store.get(self.ns['request_key'](self.token)));request['location']='ftp://192.0.2.1/else/hello.txt'
        self.store.set(self.ns['request_key'](self.token),json.dumps(request))
        self.ns['run_action'](1,self.token);self.assertEqual(self.calls,[])
        self.assertEqual(json.loads(self.store.get(self.ns['action_key'](self.token)))['error'],'source_outside_scope')
