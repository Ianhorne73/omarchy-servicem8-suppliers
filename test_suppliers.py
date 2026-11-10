import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import suppliers as s

class Response:
    def __init__(self, rows, cursor=''):
        self.data=json.dumps(rows).encode(); self.headers={'x-next-cursor':cursor}
    def read(self,n): return self.data[:n]
    def __enter__(self): return self
    def __exit__(self,*a): pass

class Tests(unittest.TestCase):
    def test_pagination_and_plain_markup(self):
        with patch.object(s.urllib.request, 'build_opener') as build:
            build.return_value.open.side_effect=[Response([{'name':'<img src="https://bad.invalid">'}],'next'),Response([{'name':'A'}])]
            rows=s.fetch('test-secret')
            self.assertEqual(len(rows),2)
            self.assertTrue(rows[0]['name'].startswith('<img'))
            for call in build.return_value.open.call_args_list:
                req=call.args[0]
                self.assertTrue(req.full_url.startswith(s.BASE+'?'))
                self.assertNotIn('test-secret',req.full_url)
                self.assertEqual(req.get_header('X-api-key'),'test-secret')
    def test_cursor_loop(self):
        with patch.object(s.urllib.request,'build_opener') as b:
            b.return_value.open.return_value=Response([], '-1')
            with self.assertRaises(ValueError): s.fetch('test')
    def test_response_bound(self):
        with patch.object(s.urllib.request,'build_opener') as b:
            response=Response([]); response.data=b'x'*(s.MAX_BYTES+1)
            b.return_value.open.return_value=response
            with self.assertRaises(ValueError): s.fetch('test')
    def test_redirect_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            s.NoRedirect().redirect_request(s.urllib.request.Request(s.BASE),io.BytesIO(),302,'',{},'https://bad.invalid')
        raised.exception.close()
    def test_url_injection(self):
        for value in ['javascript:alert(1)','file:///etc/passwd','https://a:b@example.com','https://ok.invalid/\n--arg']:
            self.assertEqual(s.action_url('website',value),'')
        for value in ['a@b.com?bcc=evil@a.com','a@b.com\nBcc:x','a@b.com&body=x']:
            self.assertEqual(s.action_url('email',value),'')
        self.assertEqual(s.action_url('email','orders@example.com'),'mailto:orders@example.com')
        self.assertEqual(s.action_url('website','example.com'),'https://example.com')
        self.assertEqual(s.action_url('phone','(07) 1234 5678'),'tel:0712345678')
    def test_permissions_cache_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch.multiple(s,CONFIG=base/'config',SHARED=base/'shared.json',CACHE=base/'cache'):
                s.save(s.SHARED,{'api_key':'test-only'})
                with patch.object(s,'fetch',return_value=[s.clean({'name':'A'})]) as fetch:
                    first=s.report(True)
                    self.assertEqual(first['error'],'')
                    self.assertEqual(s.report(),first)
                    fetch.assert_called_once()
                with patch.object(s,'fetch',side_effect=urllib.error.URLError('secret must never leak')):
                    failed=s.report(True)
                    self.assertTrue(failed['stale'])
                    self.assertEqual(len(failed['suppliers']),1)
                    self.assertNotIn('secret must',json.dumps(failed))
                with patch.object(s,'fetch',side_effect=urllib.error.HTTPError('',403,'',{},io.BytesIO())):
                    self.assertTrue(s.report(True,new_key='wrong')['error'])
                    self.assertFalse((s.CONFIG/'credentials.json').exists())
                for p in base.rglob('*.json'): self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_action_argv_and_stdin(self):
        import io
        with patch.object(s.sys, 'argv', ['suppliers.py','--action','email']), patch.object(s.sys,'stdin',io.StringIO('orders@example.com')), patch.object(s.subprocess,'run') as run:
            run.return_value.returncode=0
            self.assertEqual(s.main(),0)
            self.assertEqual(run.call_args.args[0],['xdg-open','mailto:orders@example.com'])
            self.assertNotIn('shell',run.call_args.kwargs)
        with patch.object(s.sys, 'argv', ['suppliers.py','--action','copy']), patch.object(s.sys,'stdin',io.StringIO('$(touch /tmp/no) <img>')), patch.object(s.subprocess,'run') as run:
            run.return_value.returncode=0
            self.assertEqual(s.main(),0)
            self.assertEqual(run.call_args.kwargs['input'],'$(touch /tmp/no) <img>')
    def test_multiline_map_address(self):
        import io
        address='123 Example Street\nExample City QLD 4000'
        expected='https://www.google.com/maps/search/?api=1&query=123%20Example%20Street%20Example%20City%20QLD%204000'
        self.assertEqual(s.action_url('map',address),expected)
        with patch.object(s.sys,'argv',['suppliers.py','--action','map']), patch.object(s.sys,'stdin',io.StringIO(address)), patch.object(s.subprocess,'run') as run:
            run.return_value.returncode=0
            self.assertEqual(s.main(),0)
            self.assertEqual(run.call_args.args[0],['xdg-open',expected])
    def test_shared_key_precedence_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch.multiple(s,CONFIG=base/'supplier',SHARED=base/'shared/credentials.json',CACHE=base/'cache'):
                s.save(s.CONFIG/'credentials.json',{'api_key':'old-private-key'})
                s.save(s.SHARED,{'api_key':'shared-key'})
                with patch.object(s,'fetch',return_value=[]) as fetch:
                    self.assertTrue(s.report(True)['connected'])
                    fetch.assert_called_with('shared-key')
                    self.assertTrue(s.report(True,new_key='replacement')['connected'])
                self.assertEqual(s.read(s.SHARED)['api_key'],'replacement')
                with patch.object(s,'fetch',side_effect=urllib.error.URLError('offline')):
                    self.assertFalse(s.report(True)['connected'])
                    s.report(True,new_key='bad-replacement')
                self.assertEqual(s.read(s.SHARED)['api_key'],'replacement')
    def test_corrupt_local_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.json'; path.write_text('[]')
            self.assertEqual(s.read(path),{})
    def test_quickshell_stdin_api(self):
        qml=Path(__file__).with_name('BarWidget.qml').read_text()
        self.assertNotIn('closeWriteChannel',qml)
        self.assertIn('stdinEnabled = false',qml)
    def test_dynamic_text_sinks(self):
        qml=Path(__file__).with_name('BarWidget.qml').read_text()
        self.assertEqual(qml.count('Text {'),qml.count('textFormat: Text.PlainText'))
        self.assertIn('textFormat: Text.PlainText',qml)
        # Shared tooltips/buttons only receive plugin-owned catalog strings.
        for line in qml.splitlines():
            if 'tooltipText:' in line: self.assertIn('strings.t(',line)
            if 'HeaderButton {' in line: self.assertNotIn('text: modelData',line)


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        patcher=patch.multiple(s,CONFIG=base/'config',SHARED=base/'shared/credentials.json',CACHE=base/'cache')
        patcher.start(); self.addCleanup(patcher.stop)
        s.save(s.SHARED,{'api_key':'synthetic-secret'})
        self.fields={'name':'Example Supplier','email':'orders@example.invalid','phone':'07 1234 5678', 'address':'Line 1\nLine 2','account_number':'A1','business_number':'B2'}
        self.refreshed={'suppliers':[],'error':'','connected':True}
    def test_creation_posts_only_documented_fields(self):
        uid='00000000-0000-4000-8000-000000000001'
        response=Response([]); response.status=200; response.headers={'x-record-uuid':uid}
        with patch.object(s.urllib.request,'build_opener') as build:
            build.return_value.open.return_value=response
            s.create_request('synthetic-secret',uid,self.fields)
            req=build.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(),'POST')
            self.assertEqual(req.full_url,s.BASE)
            self.assertEqual(json.loads(req.data),{**self.fields,'uuid':uid})
            self.assertNotIn('synthetic-secret',req.full_url)
            self.assertEqual(req.get_header('X-api-key'),'synthetic-secret')
    def test_success_refreshes_and_includes_created_supplier(self):
        with patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request') as post, patch.object(s,'report',return_value=self.refreshed) as refresh:
            result=s.create_supplier(self.fields)
        self.assertTrue(result['created'])
        post.assert_called_once()
        refresh.assert_called_once_with(True,key_override='synthetic-secret')
        self.assertEqual(result['supplier']['name'],self.fields['name'])
        self.assertEqual(result['report']['suppliers'][0],result['supplier'])
        pending=next(s.CACHE.glob('create-*.json'))
        self.assertEqual(pending.stat().st_mode & 0o777,0o600)
    def test_duplicate_requires_explicit_override(self):
        duplicate=s.clean({**self.fields,'name':'EXAMPLE SUPPLIER'})
        with patch.object(s,'fetch',return_value=[duplicate]), patch.object(s,'create_request') as post, patch.object(s,'report',return_value=self.refreshed):
            result=s.create_supplier(self.fields)
            self.assertFalse(result['created']); self.assertTrue(result['duplicate'])
            post.assert_not_called()
            self.assertTrue(s.create_supplier({**self.fields,'allow_duplicate':True})['created'])
            post.assert_called_once()
    def test_write_permission_failure_is_clear_and_not_success(self):
        error=urllib.error.HTTPError(s.BASE,403,'private error must not leak',{},io.BytesIO())
        with patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request',side_effect=error):
            result=s.create_supplier(self.fields)
        self.assertEqual(result,{'created':False,'error_code':'createPermission'})
        error.close()
    def test_unknown_result_is_recovered_without_second_post(self):
        with patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request',side_effect=TimeoutError) as post:
            result=s.create_supplier(self.fields)
        self.assertFalse(result['created']); post.assert_called_once()
        uid=s.read(next(s.CACHE.glob('create-*.json')))['uuid']
        row=s.clean({**self.fields,'uuid':uid})
        with patch.object(s,'existing_attempt',return_value=row) as get, patch.object(s,'create_request') as post, patch.object(s,'report',return_value=self.refreshed):
            recovered=s.create_supplier(self.fields)
        self.assertTrue(recovered['created']); post.assert_not_called()
        get.assert_called_once_with('synthetic-secret',uid)
    def test_retry_reuses_original_uuid_if_not_created(self):
        with patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request',side_effect=TimeoutError): s.create_supplier(self.fields)
        uid=s.read(next(s.CACHE.glob('create-*.json')))['uuid']
        with patch.object(s,'existing_attempt',return_value=None), patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request') as post, patch.object(s,'report',return_value=self.refreshed):
            self.assertTrue(s.create_supplier(self.fields)['created'])
        self.assertEqual(post.call_args.args[1],uid)
    def test_success_is_preserved_if_refresh_fails(self):
        with patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request'), patch.object(s,'report',return_value={'suppliers':[],'error':'offline'}):
            result=s.create_supplier(self.fields)
        self.assertTrue(result['created']); self.assertTrue(result['refresh_failed'])
        self.assertEqual(len(result['report']['suppliers']),1)
    def test_validation_never_posts_invalid_input(self):
        values=[{}, {'name':''}, {'name':'A','email':'invalid'}, {'name':'A','website':'https://bad.invalid'}, {'name':'A','phone':[]}, {'name':'A','allow_duplicate':'yes'}, {'name':'A'*201}, {'name':'A\x00B'}]
        with patch.object(s,'create_request') as post, patch.object(s,'fetch') as fetch:
            for fields in values:
                with self.subTest(fields=fields): self.assertFalse(s.create_supplier(fields)['created'])
            post.assert_not_called(); fetch.assert_not_called()
    def test_create_cli_has_bounded_private_stdin(self):
        import io
        with patch.object(s.sys,'argv',['suppliers.py','--create']), patch.object(s.sys,'stdin',io.StringIO('x'*17000)), patch.object(s.sys,'stdout',io.StringIO()) as output, patch.object(s,'create_supplier') as create:
            self.assertEqual(s.main(),0)
            create.assert_not_called()
            self.assertEqual(json.loads(output.getvalue()),{'created':False,'error_code':'invalidForm'})


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        patcher=patch.multiple(s,CONFIG=base/'config',SHARED=base/'shared/credentials.json',CACHE=base/'cache')
        patcher.start(); self.addCleanup(patcher.stop)
        s.save(s.SHARED,{'api_key':'synthetic-secret'})
        self.uid='00000000-0000-4000-8000-000000000001'
        self.row=s.clean({'uuid':self.uid,'name':'Example Supplier'})
        self.payload={'uuid':self.uid,'name':'Example Supplier','confirmation':'yes'}
    def test_exact_confirmation_is_required_before_any_network(self):
        with patch.object(s,'existing_attempt') as get, patch.object(s,'delete_request') as delete:
            for text in ['', 'Yes','YES',' yes','yes ','yesterday',True,None]:
                with self.subTest(text=text):
                    result=s.delete_supplier({**self.payload,'confirmation':text})
                    self.assertFalse(result['deleted'])
                    self.assertEqual(result['error_code'],'deleteConfirmRequired')
            get.assert_not_called(); delete.assert_not_called()
    def test_invalid_uuid_never_reaches_network(self):
        with patch.object(s,'existing_attempt') as get:
            result=s.delete_supplier({**self.payload,'uuid':'../../somewhere'})
            self.assertEqual(result['error_code'],'deleteInvalid')
            get.assert_not_called()
    def test_delete_uses_fixed_endpoint_and_header_auth(self):
        response=Response([]);response.status=200
        with patch.object(s.urllib.request,'build_opener') as build:
            build.return_value.open.return_value=response
            s.delete_request('synthetic-secret',self.uid)
            req=build.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(),'DELETE')
            self.assertEqual(req.full_url,'https://api.servicem8.com/api_1.0/supplier/'+self.uid+'.json')
            self.assertEqual(req.get_header('X-api-key'),'synthetic-secret')
            self.assertIsNone(req.data)
    def test_success_removes_supplier_from_list_and_cache(self):
        with patch.object(s,'existing_attempt',return_value=self.row), patch.object(s,'delete_request') as delete, patch.object(s,'report',return_value={'suppliers':[self.row],'error':''}) as report:
            result=s.delete_supplier(self.payload)
            self.assertTrue(result['deleted']);self.assertEqual(result['report']['suppliers'],[])
            delete.assert_called_once_with('synthetic-secret',self.uid)
            report.assert_called_once_with(True,key_override='synthetic-secret')
        cache=s.CACHE/(s.hashlib.sha256(b'synthetic-secret').hexdigest()[:24]+'.json')
        self.assertEqual(s.read(cache)['suppliers'],[])
    def test_changed_name_requires_review(self):
        with patch.object(s,'existing_attempt',return_value={**self.row,'name':'Renamed'}), patch.object(s,'delete_request') as delete:
            result=s.delete_supplier(self.payload)
            self.assertEqual(result['error_code'],'deleteChanged');delete.assert_not_called()
    def test_permission_failure_keeps_record_and_no_success(self):
        error=urllib.error.HTTPError(s.BASE,403,'private detail',{},io.BytesIO())
        with patch.object(s,'existing_attempt',return_value=self.row), patch.object(s,'delete_request',side_effect=error), patch.object(s,'report') as report:
            result=s.delete_supplier(self.payload)
            self.assertEqual(result,{'deleted':False,'error_code':'deletePermission'})
            report.assert_not_called()
        error.close()
    def test_timeout_does_not_retry_or_report_success(self):
        with patch.object(s,'existing_attempt',return_value=self.row), patch.object(s,'delete_request',side_effect=TimeoutError) as delete:
            result=s.delete_supplier(self.payload)
            self.assertEqual(result['error_code'],'deleteUncertain');delete.assert_called_once()
    def test_already_archived_or_missing_is_idempotent(self):
        for row in [None, {**self.row,'active':False}]:
            with patch.object(s,'existing_attempt',return_value=row), patch.object(s,'delete_request') as delete, patch.object(s,'report',return_value={'suppliers':[],'error':''}):
                self.assertTrue(s.delete_supplier(self.payload)['deleted']);delete.assert_not_called()
    def test_refresh_failure_does_not_undo_confirmed_delete(self):
        with patch.object(s,'existing_attempt',return_value=self.row), patch.object(s,'delete_request'), patch.object(s,'report',return_value={'suppliers':[self.row],'error':'offline'}):
            result=s.delete_supplier(self.payload)
            self.assertTrue(result['deleted']);self.assertTrue(result['refresh_failed'])
            self.assertEqual(result['report']['suppliers'],[])
    def test_cache_failure_does_not_undo_confirmed_delete(self):
        with patch.object(s,'existing_attempt',return_value=self.row), patch.object(s,'delete_request'), patch.object(s,'report',return_value={'suppliers':[],'error':''}), patch.object(s,'save',side_effect=OSError):
            self.assertTrue(s.delete_supplier(self.payload)['deleted'])
    def test_recreating_deleted_supplier_gets_new_uuid(self):
        fields={k:self.row[k] for k in s.CREATE_FIELDS}
        fingerprint=s.hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()[:24]
        account=s.hashlib.sha256(b'synthetic-secret').hexdigest()[:24]
        s.save(s.CACHE/('create-'+account+'-'+fingerprint+'.json'),{'uuid':self.uid})
        with patch.object(s,'existing_attempt',return_value={**self.row,'active':False}), patch.object(s,'fetch',return_value=[]), patch.object(s,'create_request') as post, patch.object(s,'report',return_value={'suppliers':[],'error':''}):
            result=s.create_supplier(fields)
            self.assertTrue(result['created']); self.assertNotEqual(post.call_args.args[1],self.uid)


class EditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        patcher=patch.multiple(s,CONFIG=base/'config',SHARED=base/'shared/credentials.json',CACHE=base/'cache')
        patcher.start();self.addCleanup(patcher.stop)
        s.save(s.SHARED,{'api_key':'synthetic-secret'})
        self.uid='00000000-0000-4000-8000-000000000001'
        self.row=s.clean({'uuid':self.uid,'name':'Original Supplier','email':'orders@example.invalid','phone':'123456'})
        self.original={k:self.row[k] for k in s.CREATE_FIELDS}
        self.fields={**self.original,'phone':'654321'}
        self.payload={'uuid':self.uid,'original':self.original,'fields':self.fields,'allow_duplicate':False,'confirmation':'yes'}
        self.refreshed={'suppliers':[self.row],'error':''}
    def test_edit_requires_literal_yes_before_network(self):
        with patch.object(s,'existing_attempt') as get,patch.object(s,'update_request') as update:
            for value in ['', 'Yes', 'YES', ' yes', 'yes ', 'yesterday', True, None]:
                result=s.edit_supplier({**self.payload,'confirmation':value})
                self.assertFalse(result['updated'])
                self.assertEqual(result['error_code'],'editConfirmRequired')
            missing=dict(self.payload);missing.pop('confirmation')
            self.assertFalse(s.edit_supplier(missing)['updated'])
            get.assert_not_called();update.assert_not_called()
    def test_update_uses_existing_record_post_and_only_changes(self):
        response=Response([]);response.status=200
        with patch.object(s.urllib.request,'build_opener') as build:
            build.return_value.open.return_value=response
            s.update_request('synthetic-secret',self.uid,{'email':''})
            req=build.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(),'POST')
            self.assertEqual(req.full_url,'https://api.servicem8.com/api_1.0/supplier/'+self.uid+'.json')
            self.assertEqual(json.loads(req.data),{'email':''})
            self.assertEqual(req.get_header('X-api-key'),'synthetic-secret')
    def test_success_patches_only_changed_fields_and_refreshes(self):
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'update_request') as update,patch.object(s,'report',return_value=self.refreshed):
            result=s.edit_supplier(self.payload)
        self.assertTrue(result['updated'])
        update.assert_called_once_with('synthetic-secret',self.uid,{'phone':'654321'})
        self.assertEqual(result['report']['suppliers'][0]['phone'],'654321')
        self.assertEqual(result['supplier']['uuid'],self.uid)
    def test_remote_changes_to_untouched_fields_are_preserved(self):
        with patch.object(s,'existing_attempt',return_value={**self.row,'address':'New remote address'}),patch.object(s,'update_request'),patch.object(s,'report',return_value=self.refreshed):
            result=s.edit_supplier(self.payload)
        self.assertEqual(result['supplier']['address'],'New remote address')
    def test_conflicting_changes_do_not_write(self):
        with patch.object(s,'existing_attempt',return_value={**self.row,'phone':'different'}),patch.object(s,'update_request') as update:
            result=s.edit_supplier(self.payload)
        self.assertEqual(result['error_code'],'editConflict');update.assert_not_called()
    def test_lost_response_retry_recognizes_already_applied_changes(self):
        with patch.object(s,'existing_attempt',return_value={**self.row,'phone':'654321'}),patch.object(s,'update_request') as update,patch.object(s,'report',return_value=self.refreshed):
            self.assertTrue(s.edit_supplier(self.payload)['updated'])
        update.assert_not_called()
    def test_archived_or_missing_cannot_be_updated(self):
        for row in [None,{**self.row,'active':False}]:
            with patch.object(s,'existing_attempt',return_value=row),patch.object(s,'update_request') as update:
                self.assertEqual(s.edit_supplier(self.payload)['error_code'],'editMissing');update.assert_not_called()
    def test_clear_optional_email_is_sent_as_empty_string(self):
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'fetch',return_value=[]),patch.object(s,'update_request') as update,patch.object(s,'report',return_value=self.refreshed):
            s.edit_supplier({**self.payload,'fields':{**self.original,'email':''}})
        self.assertEqual(update.call_args.args[2],{'email':''})
    def test_duplicate_check_excludes_self(self):
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'fetch',return_value=[self.row]),patch.object(s,'update_request') as update,patch.object(s,'report',return_value=self.refreshed):
            result=s.edit_supplier({**self.payload,'fields':{**self.original,'name':'Renamed Supplier'}})
        self.assertTrue(result['updated']);update.assert_called_once()
    def test_duplicate_requires_override(self):
        other=s.clean({'uuid':'00000000-0000-4000-8000-000000000002','name':'Renamed Supplier'})
        payload={**self.payload,'fields':{**self.original,'name':'Renamed Supplier'}}
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'fetch',return_value=[other]),patch.object(s,'update_request') as update,patch.object(s,'report',return_value=self.refreshed):
            self.assertTrue(s.edit_supplier(payload)['duplicate']);update.assert_not_called()
            self.assertTrue(s.edit_supplier({**payload,'allow_duplicate':True})['updated'])
    def test_permission_error_is_not_success(self):
        error=urllib.error.HTTPError(s.BASE,403,'private',{},io.BytesIO())
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'update_request',side_effect=error):
            result=s.edit_supplier(self.payload)
        self.assertEqual(result,{'updated':False,'error_code':'editPermission'});error.close()
    def test_refresh_failure_preserves_confirmed_update(self):
        with patch.object(s,'existing_attempt',return_value=self.row),patch.object(s,'update_request'),patch.object(s,'report',return_value={'suppliers':[self.row],'error':'offline'}):
            result=s.edit_supplier(self.payload)
        self.assertTrue(result['updated']);self.assertTrue(result['refresh_failed'])
        self.assertEqual(result['supplier']['phone'],'654321')
    def test_invalid_identity_or_fields_never_make_network_request(self):
        with patch.object(s,'existing_attempt') as get:
            for value in [{**self.payload,'uuid':'../unsafe'},{**self.payload,'fields':{}},{**self.payload,'fields':{**self.fields,'active':1}},{**self.payload,'original':{}},{}]:
                self.assertFalse(s.edit_supplier(value)['updated'])
        get.assert_not_called()


class PhoneActionTests(unittest.TestCase):
    def test_no_dialer_copies_number_without_opening_browser(self):
        from types import SimpleNamespace
        for handler in ['', 'google-chrome.desktop','chromium.desktop','firefox.desktop']:
            with patch.object(s.subprocess,'run',side_effect=[SimpleNamespace(stdout=handler),SimpleNamespace(returncode=0)]) as run:
                self.assertEqual(s.phone_action('07 1234 5678'),(0,'phoneCopiedNoHandler'))
                self.assertEqual(run.call_args.args[0],['wl-copy','--type','text/plain'])
                self.assertEqual(run.call_args.kwargs['input'],'07 1234 5678')
                self.assertFalse(any(c.args[0][0]=='xdg-open' for c in run.call_args_list))
    def test_configured_dialer_receives_tel_link(self):
        from types import SimpleNamespace
        with patch.object(s.subprocess,'run',side_effect=[SimpleNamespace(stdout='org.linphone.Linphone.desktop'),SimpleNamespace(returncode=0)]) as run:
            self.assertEqual(s.phone_action('07 1234 5678'),(0,''))
            self.assertEqual(run.call_args.args[0],['xdg-open','tel:0712345678'])
    def test_invalid_phone_never_spawns_process(self):
        with patch.object(s.subprocess,'run') as run:
            self.assertEqual(s.phone_action('invalid'),(1,''));run.assert_not_called()
    def test_missing_phone_utilities_fail_cleanly(self):
        with patch.object(s.subprocess,'run',side_effect=FileNotFoundError): self.assertEqual(s.phone_action('0712345678'),(1,''))

if __name__=='__main__': unittest.main()
