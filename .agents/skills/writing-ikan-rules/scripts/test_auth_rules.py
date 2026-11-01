import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / '.agents/skills/writing-ikan-rules/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('ikan_auth_validator', SCRIPTS / 'validate_rule.py')
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)
from legado_converter.converter import convert_source
from legado_converter.models import ParsedSource, SourceLocation


def base():
    return {'id':'test', 'name':'Test', 'host':'https://example.com','contentType':'novel',
            'enableSearch':False,'enableDiscover':False,'chapterList':'li','chapterName':'a@text','chapterResult':'a@href','contentItems':'#content@text'}


def errors(auth):
    rule = base()
    rule['auth'] = auth
    return [item for item in validator.validate_rule(rule) if item.level == 'error']


class AuthRulesTest(unittest.TestCase):
    def test_valid_generic_web_and_api_config(self):
        configs = [
            {'version':1, 'requiredFor':['search'], 'entries':[{'id':'web','type':'webview','url':'https://example.com/login','origins':['https://example.com'],'cookieMode':'all'}]},
            {'version':1, 'requiredFor':['all'], 'entries':[{'id':'api','type':'api','request':'https://example.com/sign-in','extract':[{'name':'accessToken','source':'body','path':'data.token'}]}], 'inject':[{'header':'authorization','template':'Bearer {{accessToken}}','origins':['https://example.com']}]},
        ]
        for config in configs:
            with self.subTest(config=config):
                self.assertFalse(errors(config))

    def test_legacy_url_warns_and_actual_cookie_is_rejected(self):
        rule = dict(base(), loginUrl='/login', cookies='sid=synthetic')
        issues = validator.validate_rule(rule)
        self.assertTrue(any(i.field == 'loginUrl' and i.level == 'warning' for i in issues))
        self.assertTrue(any(i.field == 'cookies' and i.level == 'error' for i in issues))

    def test_malformed_auth_and_scopes(self):
        for auth in [[], {'version':2}, {'version':True}, {'version':1,'requiredFor':'search'}, {'version':1,'requiredFor':['vip']}, {'version':1,'requiredFor':[{}]}, {'version':1,'entries':'web'}, {'version':1,'allowHostSwitch':'true'}]:
            with self.subTest(auth=auth): self.assertTrue(errors(auth))

    def test_cookie_modes_and_registration_origins(self):
        web = {'id':'web','type':'webview','url':'https://example.com/login','origins':['https://example.com'],'cookieMode':'all'}
        self.assertFalse(errors({'version':1,'entries':[web],'requiredFor':['search']}))
        for entry in [dict(web, origins=['https://evil.example']),dict(web, type='api'),dict(web, extract=[{'name':'token'}]),dict(web, origins=['http://example.com'])]:
            self.assertTrue(errors({'version':1,'entries':[entry]}))
        self.assertTrue(errors({'version':1,'registration':{'url':'https://example.com/register','origins':['https://evil.example']}}))
        self.assertFalse(errors({'version':1,'registration':{'url':'https://example.com/register','origins':['https://example.com']}}))

    def test_global_credentials_rejected_without_echo(self):
        rule = dict(base(), userAgent=json.dumps({'User-Agent':'Fixture','Cookie':'sid=synthetic-secret'}))
        issues = validator.validate_rule(rule)
        self.assertTrue(any(i.field == 'userAgent' and i.level == 'error' for i in issues))
        self.assertNotIn('synthetic-secret', str(issues))

    def test_converter_migrates_static_login_and_strips_credentials(self):
        source = {'bookSourceName':'Fixture','bookSourceUrl':'https://example.com','loginUrl':'/login','header':json.dumps({'User-Agent':'Fixture','Cookie':'sid=synthetic-secret'})}
        result = convert_source(ParsedSource(source, SourceLocation('fixture')))
        self.assertNotIn('loginUrl', result.rule)
        entry = result.rule['auth']['entries'][0]
        self.assertEqual(entry['url'], 'https://example.com/login')
        self.assertEqual(entry['cookieMode'], 'all')
        self.assertNotIn('requiredFor', result.rule['auth'])
        self.assertNotIn('synthetic-secret', json.dumps(result.rule))
        self.assertNotIn('synthetic-secret', str(result.diagnostics))
        self.assertEqual(json.loads(result.rule['userAgent']), {'User-Agent':'Fixture'})

    def test_converter_does_not_guess_scripted_login(self):
        source = {'bookSourceName':'Fixture','bookSourceUrl':'https://example.com','loginUrl':'function login(){java.post("https://example.com/login")}'}
        result = convert_source(ParsedSource(source, SourceLocation('fixture')))
        self.assertNotIn('auth', result.rule)
        self.assertTrue(any(d.code == 'conversion.login_manual' for d in result.diagnostics))

    def test_injection_requires_https_scope_and_credential_template(self):
        self.assertTrue(errors({'version':1,'inject':[{'header':'authorization','template':'synthetic-token','origins':['http://example.com']}]}))
        self.assertFalse(errors({'version':1,'inject':[{'header':'authorization','template':'Bearer {{accessToken}}','origins':['https://example.com']}]}))
        self.assertTrue(errors({'version':1,'entries':[{'type':[]}]}))

    def test_public_defaults_are_api_strings_only(self):
        entry = {'id':'api','type':'api','fields':[{'name':'username','defaultValue':'public-fixture'},{'name':'password','secret':True,'defaultValue':'public-password-fixture'}]}
        self.assertFalse(errors({'version':1,'entries':[entry]}))
        self.assertTrue(errors({'version':1,'entries':[dict(entry, type='manual')]}))
        self.assertTrue(errors({'version':1,'entries':[dict(entry, fields=[{'name':'password','defaultValue':123}])]}))
        self.assertTrue(errors({'version':1,'entries':[dict(entry, fields='invalid')]}))

    def test_backup_host_scope_and_schema(self):
        rule = dict(base(), backupHosts=['https://mirror.example.net','https://mirror.example.org/'])
        self.assertFalse([i for i in validator.validate_rule(rule) if i.level == 'error'])
        for value in ['https://mirror.example.net', ['https://user:pass@mirror.example.net'], ['https://mirror.example.net/path'], ['http://mirror.example.net'], [1], ['https://mirror.example.net?q=1'], ['https://mirror{}.example'.format(i) for i in range(9)]]:
            with self.subTest(value=value):
                self.assertTrue([i for i in validator.validate_rule(dict(base(), backupHosts=value)) if i.level == 'error'])

    def test_skill_links_and_contract(self):
        skill = ROOT/'.agents/skills/writing-ikan-rules/SKILL.md'
        text = skill.read_text()
        self.assertIn('cookieMode: "all"', text)
        self.assertIn('requiredFor', text)
        self.assertIn('chapterLock', text)
        self.assertTrue((skill.parent/'../../../rules/09-authentication.md').resolve().is_file())


if __name__ == '__main__':
    unittest.main()
