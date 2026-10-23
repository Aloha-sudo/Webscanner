import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('scanner_cli', Path(__file__).resolve().parents[2] / 'cli/webscanner.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CliTests(unittest.TestCase):
    def test_one_command_creates_context_and_submits_scan(self):
        client = Mock()
        client.request.side_effect = [[], {'id': 7, 'name': 'Lab'}, {'id': 8, 'name': 'Office'}, {'id': 10}]
        args = cli.parser().parse_args(['scan', '10.0.0.0/24', '--project', 'Lab', '--part', 'Office', '--source', '10.0.0.1', '--create-missing'])
        result = cli.run(args, client)
        self.assertEqual(result['id'], 10)
        self.assertEqual(client.request.call_args.args, ('POST', '/scans', {
            'target': '10.0.0.0/24', 'scan_type': 'quick', 'speed': 'normal',
            'project_id': 7, 'network_part_id': 8, 'source_host': '10.0.0.1'}))

    def test_missing_part_does_not_silently_create_without_flag(self):
        client = Mock()
        client.request.return_value = [{'id': 7, 'name': 'Lab', 'parts': []}]
        with self.assertRaises(cli.ApiError):
            cli.context(client, 'Lab', 'Office')
        self.assertEqual(client.request.call_count, 1)

    def test_retry_only_sends_explicit_overrides(self):
        client = Mock()
        cli.run(cli.parser().parse_args(['scans','retry','93','--source','10.0.0.2']), client)
        client.request.assert_called_once_with('POST','/scans/93/retry',{'source_host':'10.0.0.2'})

    def test_names_are_case_and_whitespace_normalized(self):
        client = Mock()
        client.request.return_value = [{'id':7,'name':'  Lab  Team','parts':[{'id':8,'name':' Office '}]}]
        self.assertEqual(cli.context(client,'lab team','OFFICE',True), {'project_id':7,'network_part_id':8})
        self.assertEqual(client.request.call_count, 1)

    def test_client_sends_json_without_operator_credentials(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{"id": 1}'
        with patch.object(cli.urllib.request, 'urlopen', return_value=response) as opener:
            result=cli.Client('http://localhost:3000').request('POST','/scans',{'target':'10.0.0.1'})
            request=opener.call_args.args[0]
            self.assertEqual(request.full_url,'http://localhost:3000/api/scans')
            self.assertIsNone(request.get_header('Authorization'))
            self.assertIn(b'10.0.0.1',request.data)
            self.assertEqual(result,{'id':1})
