#!/usr/bin/env python3
"""ServiceM8 supplier directory with explicit creation, editing and confirmed deletion. Credentials never enter argv or output."""
import argparse
import datetime as dt
import hashlib
import fcntl
import uuid
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.servicem8.com/api_1.0/supplier.json'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'omarchy/servicem8-suppliers'
SHARED = Path.home()/'.config/omarchy/servicem8/credentials.json'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'omarchy/servicem8-suppliers'
MAX_BYTES = 4 * 1024 * 1024
FIELDS = ('name', 'email', 'phone', 'address', 'account_number', 'business_number', 'website', 'notes')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)

def read(path):
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: raise ValueError('File too large')
        value = json.loads(data)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}

def save(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream: json.dump(data, stream)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def clean(row):
    result = {k: str(row.get(k) or '').replace('\x00', '')[:2048] for k in FIELDS}
    result['uuid'] = str(row.get('uuid', ''))[:64]
    return result

def fetch(key):
    cursor, seen, result = '-1', set(), []
    opener = urllib.request.build_opener(NoRedirect())
    for page in range(100):
        if cursor in seen: raise ValueError('Repeated pagination cursor')
        seen.add(cursor)
        url = BASE + '?' + urllib.parse.urlencode({'$filter':'active eq 1', 'cursor':cursor})
        req = urllib.request.Request(url, headers={'X-API-Key':key, 'Accept':'application/json', 'User-Agent':'Omarchy-Suppliers/1.0'})
        with opener.open(req, timeout=15) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES: raise ValueError('Response too large')
            rows = json.loads(data)
            cursor = response.headers.get('x-next-cursor', '')
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows): raise ValueError('Invalid supplier list')
        result.extend(clean(r) for r in rows if str(r.get('active', 1)) == '1')
        if len(result) > 10000 or len(cursor) > 512: raise ValueError('Directory limit reached')
        if len(json.dumps(result).encode()) > MAX_BYTES - 4096: raise ValueError('Directory size limit reached')
        if not cursor: return sorted(result, key=lambda r:r['name'].casefold())
    raise ValueError('Pagination limit reached')

def action_url(kind, value):
    value = value.strip()
    if kind == 'map': value = ' '.join(value.split())
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value): return ''
    if kind == 'website':
        if '://' not in value: value = 'https://' + value
        try:
            u = urllib.parse.urlsplit(value)
            port = u.port  # Validate malformed port/scheme-shaped input.
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password: return ''
            if any(c.isspace() for c in value): return ''
            return value
        except ValueError: return ''
    if kind == 'email':
        if value.count('@') != 1 or any(c.isspace() for c in value) or any(c in value for c in '?&#,;'): return ''
        return 'mailto:' + urllib.parse.quote(value, safe='@.+-_')
    if kind == 'phone':
        number = ''.join(c for c in value if c in '+0123456789')
        return 'tel:' + number if sum(c.isdigit() for c in number) >= 5 else ''
    if kind == 'map': return 'https://www.google.com/maps/search/?api=1&query=' + urllib.parse.quote(value, safe='')
    return ''

def report(force=False, new_key=None, key_override=None):
    key = new_key or key_override or read(SHARED).get('api_key') or read(CONFIG/'credentials.json').get('api_key')
    if not isinstance(key, str) or not key.strip(): return {'suppliers':[], 'error':'', 'needs_setup':True, 'connected':False}
    key = key.strip()
    path = CACHE/(hashlib.sha256(key.encode()).hexdigest()[:24] + '.json')
    cached = read(path)
    now = dt.datetime.now(dt.timezone.utc)
    try: age = (now - dt.datetime.fromisoformat(cached.get('updated',''))).total_seconds()
    except (ValueError, TypeError): age = 1e10
    if not force and new_key is None and 0 <= age < 900: return {**cached, 'connected':True}
    try:
        rows = fetch(key)
        data = {'suppliers':rows, 'updated':now.isoformat(), 'error':'', 'needs_setup':False, 'connected':True}
        if new_key or not read(SHARED).get('api_key'): save(SHARED, {'api_key':key})
        save(path, data)
        return data
    except urllib.error.HTTPError as e:
        error = {401:'API key rejected. Check your connection.',403:'Supplier access denied. Enable Suppliers and grant read_suppliers access.',429:'ServiceM8 rate limit reached. Try again later.'}.get(e.code, 'ServiceM8 request failed. Try again later.')
    except (OSError, ValueError, urllib.error.URLError): error = 'Could not refresh suppliers. Check your connection and try again.'
    return {**cached, 'suppliers':cached.get('suppliers', []), 'error':error, 'needs_setup':False, 'stale':bool(cached), 'connected':False}

CREATE_FIELDS = ('name', 'email', 'phone', 'address', 'account_number', 'business_number')
CREATE_LIMITS = {'name':200, 'email':254, 'phone':100, 'address':2048, 'account_number':100, 'business_number':100}

class FormError(ValueError):
    pass

def validate_supplier(payload):
    if not isinstance(payload, dict) or set(payload) - set(CREATE_FIELDS) - {'allow_duplicate'}:
        raise FormError('invalidForm')
    if not isinstance(payload.get('allow_duplicate', False), bool): raise FormError('invalidForm')
    fields = {}
    for field in CREATE_FIELDS:
        value = payload.get(field, '')
        if not isinstance(value, str): raise FormError('invalidForm')
        value = value.strip()
        if len(value) > CREATE_LIMITS[field] or any(ord(c) < 32 and not (field == 'address' and c in '\r\n\t') for c in value):
            raise FormError('invalidForm')
        fields[field] = value
    if not fields['name']: raise FormError('nameRequired')
    if fields['email'] and not action_url('email', fields['email']): raise FormError('invalidEmail')
    return fields

def create_request(key, record_id, fields):
    request = urllib.request.Request(BASE, data=json.dumps({**fields, 'uuid':record_id}).encode(), method='POST', headers={
        'X-API-Key':key, 'Accept':'application/json', 'Content-Type':'application/json', 'User-Agent':'Omarchy-Suppliers/1.1'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.status not in (200, 201, 204): raise ValueError('Unexpected creation response')
        received = response.headers.get('x-record-uuid', '')
        if received and str(uuid.UUID(received)) != record_id: raise ValueError('Unexpected record UUID')
        if len(response.read(MAX_BYTES + 1)) > MAX_BYTES: raise ValueError('Response too large')

def existing_attempt(key, record_id):
    url = BASE.replace('/supplier.json', '/supplier/' + str(uuid.UUID(record_id)) + '.json')
    req = urllib.request.Request(url, headers={'X-API-Key':key, 'Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES: raise ValueError('Response too large')
            row = json.loads(raw)
            if not isinstance(row, dict) or str(row.get('uuid')) != record_id: raise ValueError('Invalid record')
            return {**clean(row), 'active':str(row.get('active', 1)) == '1'}
    except urllib.error.HTTPError as error:
        if error.code == 404: return None
        raise

def create_supplier(payload):
    """Only called after the user presses Save. Never automatically retry POST."""
    try:
        fields = validate_supplier(payload)
        key = read(SHARED).get('api_key') or read(CONFIG/'credentials.json').get('api_key')
        if not isinstance(key, str) or not key.strip(): return {'created':False, 'error_code':'notConnected'}
        key = key.strip()
        account = hashlib.sha256(key.encode()).hexdigest()[:24]
        fingerprint = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:24]
        CACHE.mkdir(parents=True, mode=0o700, exist_ok=True)
        CACHE.chmod(0o700)
        path = CACHE / ('create-' + account + '-' + fingerprint + '.json')
        # Serialize repeated clicks and simultaneous panel instances.
        with (CACHE/('create-' + account + '.lock')).open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            attempt = read(path)
            record_id = str(uuid.UUID(attempt['uuid'])) if attempt.get('uuid') else str(uuid.uuid4())
            existing = existing_attempt(key, record_id) if attempt else None
            if existing is not None and existing.get('active') is False:
                record_id, existing = str(uuid.uuid4()), None
            if existing is None:
                rows = fetch(key)
                duplicates = [r for r in rows if r['name'].casefold() == fields['name'].casefold() or (fields['email'] and r['email'].casefold() == fields['email'].casefold())]
                if duplicates and not payload.get('allow_duplicate', False):
                    return {'created':False, 'error_code':'duplicateFound', 'duplicate':True}
                # Persist the UUID before posting, so a lost response can be recovered on Retry.
                save(path, {'uuid':record_id})
                create_request(key, record_id, fields)
                existing = clean({**fields, 'uuid':record_id})
            refreshed = report(True, key_override=key)
            rows = refreshed.get('suppliers', [])
            if not any(r.get('uuid') == record_id for r in rows):
                rows = sorted(rows + [existing], key=lambda r:r['name'].casefold())
                refreshed = {**refreshed, 'suppliers':rows}
            return {'created':True, 'supplier':existing, 'report':refreshed, 'refresh_failed':bool(refreshed.get('error'))}
    except FormError as error:
        return {'created':False, 'error_code':str(error)}
    except urllib.error.HTTPError as error:
        code = {400:'createRejected',401:'createUnauthorized',403:'createPermission',429:'createRateLimit'}.get(error.code, 'createUncertain')
        return {'created':False, 'error_code':code}
    except (OSError, ValueError, urllib.error.URLError):
        return {'created':False, 'error_code':'createUncertain'}

def update_request(key, record_id, changes):
    url = BASE.replace('/supplier.json', '/supplier/' + str(uuid.UUID(record_id)) + '.json')
    req = urllib.request.Request(url, data=json.dumps(changes).encode(), method='POST', headers={
        'X-API-Key':key, 'Accept':'application/json', 'Content-Type':'application/json', 'User-Agent':'Omarchy-Suppliers/1.3'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
        if response.status not in (200, 204): raise ValueError('Unexpected update response')
        if len(response.read(MAX_BYTES + 1)) > MAX_BYTES: raise ValueError('Response too large')

def edit_supplier(payload):
    try:
        if not isinstance(payload, dict) or set(payload) != {'uuid','original','fields','allow_duplicate','confirmation'}:
            return {'updated':False, 'error_code':'editInvalid'}
        if payload.get('confirmation') != 'yes': return {'updated':False, 'error_code':'editConfirmRequired'}
        if not isinstance(payload['uuid'], str): return {'updated':False, 'error_code':'editInvalid'}
        try: record_id = str(uuid.UUID(payload['uuid']))
        except ValueError: return {'updated':False, 'error_code':'editInvalid'}
        if not isinstance(payload['allow_duplicate'], bool): raise FormError('invalidForm')
        if not isinstance(payload['fields'], dict) or set(payload['fields']) != set(CREATE_FIELDS): raise FormError('invalidForm')
        fields = validate_supplier(payload['fields'])
        original = payload['original']
        if not isinstance(original, dict) or set(original) != set(CREATE_FIELDS) or any(not isinstance(v, str) or len(v)>2048 for v in original.values()):
            return {'updated':False, 'error_code':'editInvalid'}
        changes = {k:v for k,v in fields.items() if v != original[k].strip()}
        key = read(SHARED).get('api_key') or read(CONFIG/'credentials.json').get('api_key')
        if not isinstance(key, str) or not key.strip(): return {'updated':False, 'error_code':'notConnected'}
        key = key.strip()
        account = hashlib.sha256(key.encode()).hexdigest()[:24]
        CACHE.mkdir(parents=True, mode=0o700, exist_ok=True)
        CACHE.chmod(0o700)
        with (CACHE/('create-' + account + '.lock')).open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = existing_attempt(key, record_id)
            if current is None or current.get('active') is False: return {'updated':False, 'error_code':'editMissing'}
            if any(current[k].strip() not in (original[k].strip(), v) for k,v in changes.items()):
                return {'updated':False, 'error_code':'editConflict'}
            pending = {k:v for k,v in changes.items() if current[k].strip() != v}
            if pending:
                if 'name' in pending or 'email' in pending:
                    rows = fetch(key)
                    duplicates = [r for r in rows if r['uuid'] != record_id and (
                        ('name' in pending and r['name'].casefold() == fields['name'].casefold()) or
                        ('email' in pending and fields['email'] and r['email'].casefold() == fields['email'].casefold()))]
                    if duplicates and not payload['allow_duplicate']:
                        return {'updated':False, 'error_code':'duplicateFound', 'duplicate':True}
                update_request(key, record_id, pending)
            # Retrying a lost response detects already-applied changes above.
            edited = clean({**current, **changes, 'uuid':record_id})
            refreshed = report(True, key_override=key)
            refreshed['suppliers'] = sorted([r for r in refreshed.get('suppliers', []) if r.get('uuid') != record_id] + [edited], key=lambda r:r['name'].casefold())
            if refreshed.get('error'): refreshed['updated'] = ''
            try: save(CACHE/(account+'.json'), refreshed)
            except OSError: pass
            return {'updated':True, 'supplier':edited, 'report':refreshed, 'refresh_failed':bool(refreshed.get('error'))}
    except FormError as error:
        return {'updated':False, 'error_code':str(error)}
    except urllib.error.HTTPError as error:
        code = {400:'createRejected',401:'createUnauthorized',403:'editPermission',404:'editMissing',429:'createRateLimit'}.get(error.code,'editUncertain')
        return {'updated':False, 'error_code':code}
    except (OSError, ValueError, urllib.error.URLError):
        return {'updated':False, 'error_code':'editUncertain'}

def delete_request(key, record_id):
    url = BASE.replace('/supplier.json', '/supplier/' + str(uuid.UUID(record_id)) + '.json')
    req = urllib.request.Request(url, method='DELETE', headers={'X-API-Key':key, 'Accept':'application/json', 'User-Agent':'Omarchy-Suppliers/1.2'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
            if response.status not in (200, 204): raise ValueError('Unexpected deletion response')
            if len(response.read(MAX_BYTES + 1)) > MAX_BYTES: raise ValueError('Response too large')
    except urllib.error.HTTPError as error:
        if error.code != 404: raise
        # The record is already absent: the requested final state is satisfied.

def delete_supplier(payload):
    """Require the literal confirmation in the backend as well as in the UI."""
    try:
        if not isinstance(payload, dict) or set(payload) != {'uuid','name','confirmation'}:
            return {'deleted':False, 'error_code':'deleteInvalid'}
        if payload.get('confirmation') != 'yes': return {'deleted':False, 'error_code':'deleteConfirmRequired'}
        if not isinstance(payload['uuid'], str) or not isinstance(payload['name'], str) or not payload['name'] or len(payload['name']) > 2048:
            return {'deleted':False, 'error_code':'deleteInvalid'}
        try: record_id = str(uuid.UUID(payload['uuid']))
        except ValueError: return {'deleted':False, 'error_code':'deleteInvalid'}
        key = read(SHARED).get('api_key') or read(CONFIG/'credentials.json').get('api_key')
        if not isinstance(key, str) or not key.strip(): return {'deleted':False, 'error_code':'notConnected'}
        key = key.strip()
        account = hashlib.sha256(key.encode()).hexdigest()[:24]
        CACHE.mkdir(parents=True, mode=0o700, exist_ok=True)
        CACHE.chmod(0o700)
        with (CACHE/('create-' + account + '.lock')).open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            row = existing_attempt(key, record_id)
            if row is not None and row.get('active') is not False:
                if row['name'] != payload['name']: return {'deleted':False, 'error_code':'deleteChanged'}
                delete_request(key, record_id)
            # Invalidate the old cache and remove the confirmed deletion even if
            # the following list refresh cannot reach ServiceM8.
            path = CACHE/(account + '.json')
            cached = read(path)
            if cached:
                cached['suppliers'] = [r for r in cached.get('suppliers', []) if r.get('uuid') != record_id]
                cached['updated'] = ''
                try: save(path, cached)
                except OSError: pass
            refreshed = report(True, key_override=key)
            refreshed['suppliers'] = [r for r in refreshed.get('suppliers', []) if r.get('uuid') != record_id]
            if refreshed.get('error'): refreshed['updated'] = ''
            try: save(path, refreshed)
            except OSError: pass  # A local cache failure cannot undo a confirmed remote deletion.
            return {'deleted':True, 'report':refreshed, 'refresh_failed':bool(refreshed.get('error'))}
    except urllib.error.HTTPError as error:
        code = {400:'deleteRejected',401:'createUnauthorized',403:'deletePermission',429:'createRateLimit'}.get(error.code, 'deleteUncertain')
        return {'deleted':False, 'error_code':code}
    except (OSError, ValueError, urllib.error.URLError):
        return {'deleted':False, 'error_code':'deleteUncertain'}

def phone_action(value):
    """Do not let xdg-open fall back to a browser when no dialer exists."""
    url = action_url('phone', value)
    if not url: return 1, ''
    try:
        handler = subprocess.run(['xdg-mime','query','default','x-scheme-handler/tel'], capture_output=True, text=True, timeout=3).stdout.strip()
        browser = any(name in handler.lower() for name in ('chrome','chromium','firefox','brave','vivaldi','edge','opera','browser'))
        if handler.endswith('.desktop') and '/' not in handler and not browser:
            return subprocess.run(['xdg-open',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode, ''
        result = subprocess.run(['wl-copy','--type','text/plain'],input=value.strip(),text=True)
        return result.returncode, 'phoneCopiedNoHandler' if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired): return 1, ''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--setup',action='store_true')
    parser.add_argument('--create',action='store_true')
    parser.add_argument('--delete',action='store_true')
    parser.add_argument('--edit',action='store_true')
    parser.add_argument('--action',choices=['website','email','phone','map','copy'])
    args=parser.parse_args()
    if args.edit:
        try:
            raw = sys.stdin.read(32769)
            if len(raw) > 32768: raise ValueError('Input too large')
            result = edit_supplier(json.loads(raw))
        except (ValueError, OSError): result = {'updated':False, 'error_code':'editInvalid'}
        print(json.dumps(result))
        return 0
    if args.delete:
        try:
            raw = sys.stdin.read(8193)
            if len(raw) > 8192: raise ValueError('Input too large')
            result = delete_supplier(json.loads(raw))
        except (ValueError, OSError): result = {'deleted':False, 'error_code':'deleteInvalid'}
        print(json.dumps(result))
        return 0
    if args.create:
        try:
            raw = sys.stdin.read(16385)
            if len(raw) > 16384: raise ValueError('Input too large')
            result = create_supplier(json.loads(raw))
        except (ValueError, OSError): result = {'created':False, 'error_code':'invalidForm'}
        print(json.dumps(result))
        return 0
    if args.action:
        value=sys.stdin.read(32769)
        if len(value)>32768: return 1
        if args.action=='phone':
            code, notice = phone_action(value)
            print(json.dumps({'notice_code':notice}))
            return code
        if args.action=='copy':
            return subprocess.run(['wl-copy','--type','text/plain'],input=value,text=True).returncode
        url=action_url(args.action,value)
        if not url: return 1
        return subprocess.run(['xdg-open',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
    key=None
    if args.setup:
        key=sys.stdin.read(4097).strip()
        if not key or len(key)>4096:
            print(json.dumps({'suppliers':[], 'error':'Enter a valid API key.', 'needs_setup':True, 'connected':False})); return 1
    print(json.dumps(report(args.force,key)))
    return 0

if __name__=='__main__': sys.exit(main())
