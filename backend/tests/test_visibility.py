import unittest
from app.reports.visibility import build_visibility
from app.schemas.scan import TeamMetadata
from pydantic import ValidationError


def report(id,hosts,**kwargs):
    return {'id':id,'target':f'report{id}','project':'client','network':'office','source_host':f'point{id}','hosts':hosts,**kwargs}

class VisibilityTests(unittest.TestCase):
    def test_union_and_missing_is_unknown(self):
        a=report(1,[{'ip':'10.0.0.1','ports':[{'port':22,'protocol':'tcp','service':'ssh'}]}])
        b=report(2,[{'ip':'10.0.0.2','ports':[{'port':443,'protocol':'tcp'}]}])
        result=build_visibility([a,b])
        service=next(r for r in result['rows'] if r['ip']=='10.0.0.1' and r['port']==22)
        self.assertEqual([c['state'] for c in service['cells']],['found','unknown'])
        self.assertEqual(len(result['columns']),2)
    def test_confirmed_scope_distinguishes_not_found_and_not_tested(self):
        a=report(1,[{'ip':'10.0.0.1','ports':[{'port':22,'protocol':'tcp'},{'port':443,'protocol':'tcp'}]}])
        b=report(2,[],scope_confirmed=True,scope_targets='10.0.0.0/24',scope_ports='22')
        rows=build_visibility([a,b])['rows']
        self.assertEqual(next(r for r in rows if r['port']==22)['cells'][1]['state'],'not_found')
        self.assertEqual(next(r for r in rows if r['port']==443)['cells'][1]['state'],'not_tested')
    def test_same_ip_in_other_network_cannot_merge(self):
        with self.assertRaises(ValueError):build_visibility([report(1,[]),report(2,[],network='other')])
    def test_same_port_different_protocol_and_sources_preserved(self):
        a=report(1,[{'ip':'10.0.0.1','ports':[{'port':53,'protocol':'tcp'},{'port':53,'protocol':'udp'}]}])
        result=build_visibility([a])
        self.assertEqual(len(result['rows']),3)
        self.assertEqual(result['columns'][0]['source_host'],'point1')
    def test_hosts_without_ports_are_visible(self):
        result=build_visibility([report(1,[{'ip':'10.0.0.5','ports':[]}])])
        self.assertEqual(result['rows'][0]['protocol'],'host')
        self.assertEqual(result['rows'][0]['cells'][0]['state'],'found')
    def test_exclusions_do_not_become_not_found(self):
        a=report(1,[{'ip':'10.0.0.1','ports':[{'port':22,'protocol':'tcp'}]}])
        b=report(2,[],scope_confirmed=True,scope_targets='10.0.0.0/24',scope_ports='22',exclude_ports='22')
        self.assertEqual(next(r for r in build_visibility([a,b])['rows'] if r['port']==22)['cells'][1]['state'],'not_tested')
    def test_scope_is_validated(self):
        TeamMetadata(scope_targets='10.0.0.0/24',scope_ports='1-65535')
        with self.assertRaises(ValidationError):TeamMetadata(scope_targets='invalid')
        with self.assertRaises(ValidationError):TeamMetadata(scope_ports='65536')

    def test_metadata_cannot_store_nul_byte(self):
        with self.assertRaises(ValidationError):
            TeamMetadata(source_host='host\x00bad')

    def test_team_import_metadata_needs_no_scope(self):
        data=TeamMetadata.model_validate_json('{"project":"client","network":"office","source_host":"host1","scope_targets":null,"scope_ports":null,"scope_confirmed":false}')
        self.assertIsNone(data.scope_ports)
        self.assertIsNone(data.scope_targets)
        self.assertFalse(data.scope_confirmed)

    def test_whole_project_keeps_overlapping_addresses_separate(self):
        host={'ip':'10.0.0.1','ports':[{'port':22,'protocol':'tcp'}]}
        a=report(1,[host],network='Office',network_part_id=10,project_id=1)
        b=report(2,[host],network='Branch',network_part_id=11,project_id=1)
        result=build_visibility([a,b],whole_project=True)
        services=[r for r in result['rows'] if r['port']==22]
        self.assertEqual(len(services),2)
        self.assertNotEqual(services[0]['device_id'],services[1]['device_id'])
        self.assertEqual({r['network'] for r in services},{'Office','Branch'})
        self.assertEqual(result['columns'][1]['network'],'Branch')
    def test_explicit_shared_address_space_compares_across_parts(self):
        a=report(1,[{'ip':'10.0.0.1','ports':[{'port':22,'protocol':'tcp'}]}],network='Office',network_part_id=10,project_id=1)
        b=report(2,[{'ip':'10.0.0.1','ports':[{'port':443,'protocol':'tcp'}]}],network='Servers',network_part_id=11,project_id=1,scope_confirmed=True,scope_targets='10.0.0.0/24',scope_ports='22,443')
        result=build_visibility([a,b],whole_project=True,merge_parts=True)
        ssh=next(r for r in result['rows'] if r['port']==22)
        self.assertEqual([c['state'] for c in ssh['cells']],['found','not_found'])
        self.assertEqual(len({r['device_id'] for r in result['rows']}),1)
    def test_whole_project_never_accepts_another_project(self):
        with self.assertRaises(ValueError):
            build_visibility([report(1,[],project_id=1),report(2,[],project_id=2)],whole_project=True,merge_parts=True)
