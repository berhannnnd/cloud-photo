"""Subprocess adapter for the provider's supported CLI, never internal SDK/HTTP."""
import json
from pathlib import Path
import subprocess
import sys
from .provider_lock import provider_lock


def parse_receipt(text):
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        candidates = []
        for line in text.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'schemaVersion' in value and 'status' in value:
                    candidates.append(value)
            except json.JSONDecodeError:
                pass
        if len(candidates) != 1:
            raise ValueError('provider did not return exactly one JSON receipt')
        result = candidates[0]
    if not isinstance(result, dict) or 'status' not in result:
        raise ValueError('invalid provider receipt')
    return result


def arguments(params):
    args = []
    for key, value in params.items():
        if value is None:
            continue
        values = value if key == 'step' else [value]
        for item in values:
            args.extend(['--' + key, json.dumps(item, ensure_ascii=False, separators=(',', ':'))
                         if isinstance(item, (dict, list, bool)) else str(item)])
    return args


class Cloud:
    def __init__(self, skill_dir, profile='default', python=None, timeout=120):
        self.root = Path(skill_dir).resolve()
        self.profile = profile
        self.python = python or sys.executable
        self.timeout = timeout
        self.discovered = False

    def call(self, domain, action, params=None):
        entry = self.root / 'scripts' / ('cm_cloud_' + domain + '_api.py')
        if domain not in ('cli', 'files', 'album', 'operation') or not entry.is_file():
            raise ValueError('unsupported/missing public CLI entrypoint')
        params = {**(params or {}), 'format': 'json'}
        if domain != 'cli' or action == 'orchestrate':
            params['profile'] = self.profile
        argv = [self.python, str(entry), action, *arguments(params)]
        try:
            with provider_lock(self.root.name, self.profile, self.timeout):
                response = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        except TimeoutError:
            return {'status': 'FAILED', 'data': None, 'error': {'code': 'LOCAL_PROVIDER_BUSY', 'retryable': True}, 'nextAction': None}
        except subprocess.TimeoutExpired:
            return {'status': 'UNKNOWN', 'data': None, 'error': {'code': 'CLI_TIMEOUT'}, 'nextAction': None}
        # Never expose stderr: SDK diagnostics can contain identity material.
        receipt = parse_receipt(response.stdout)
        if response.returncode and receipt['status'] == 'SUCCESS':
            raise ValueError('CLI exit status conflicts with receipt')
        return receipt

    def capability(self, command, params=None):
        if not self.discovered:
            discovery = self.call('cli', 'capabilities')
            if discovery['status'] != 'SUCCESS':
                raise ValueError('provider capability discovery failed')
            self.discovered = True
        result = self.call('cli', 'schema', {'command-id': command})
        data = result.get('data') or {}
        if result['status'] != 'SUCCESS':
            raise ValueError('provider capability discovery failed: ' + command)
        if data.get('shared'):
            # Shared commands have no top-level capability; select the exact
            # public scenario using its declared selectors, not any enabled one.
            if params is None:
                raise ValueError('scenario parameters required for shared command: ' + command)
            def matches(scene):
                selectors = scene.get('selector')
                if not isinstance(selectors, list) or not selectors:
                    return False
                for rule in selectors:
                    if not isinstance(rule, dict) or set(rule) - {'field', 'equals', 'presence'}:
                        return False
                    field = rule.get('field')
                    if not isinstance(field, str) or ('equals' not in rule and 'presence' not in rule):
                        return False
                    if 'equals' in rule and (field not in params or params[field] != rule['equals']):
                        return False
                    if 'presence' in rule:
                        if rule['presence'] not in ('present', 'absent'):
                            return False
                        if (field in params) != (rule['presence'] == 'present'):
                            return False
                return True
            selected = [scene for scene in data.get('scenes', []) if matches(scene)]
            if len(selected) != 1 or str(selected[0].get('capability', '')).lower() != 'enabled':
                raise ValueError('provider scenario unavailable or ambiguous: ' + command)
            result = {**result, 'data': {**data, 'selectedScenarioId': selected[0].get('scenarioId'),
                                       'schema': selected[0]['schema'], 'capability': selected[0]['capability']}}
        elif str(data.get('capability', '')).lower() != 'enabled':
            raise ValueError('provider capability unavailable: ' + command)
        return result


def scan(cloud, output, filters, max_pages=100, resume=False, source="search"):
    from ..storage import atomic, read, now
    if not isinstance(filters, dict) or 'cursor' in filters or max_pages < 1:
        raise ValueError('filters must be an object without cursor; max-pages must be positive')
    if source not in ('search', 'list'):
        raise ValueError('scan source must be search or list')
    schema = cloud.capability('files.' + source)
    maximum = (schema.get('data', {}).get('schema', {}).get('properties', {}).get('pageSize', {}).get('maximum'))
    if maximum and filters.get('pageSize', 10) > maximum:
        raise ValueError(f'{source} pageSize exceeds provider maximum {maximum}')
    rows, cursor, visited = [], None, set()
    if resume:
        saved = read(output)
        if saved.get('source_command', 'search') != source or saved.get('source') != filters or saved.get('profile') != cloud.profile or saved.get('skill_dir') != str(cloud.root):
            raise ValueError('scan scope/profile changed')
        if saved.get('page', {}).get('complete'):
            return {'status': 'SUCCESS', 'complete': True, 'loaded': len(saved['data']['items']), 'output': str(output)}
        rows = saved['data']['items']
        cursor = saved['page'].get('nextCursor')
    complete = False
    last = None
    def checkpoint(status, next_cursor, error=None):
        atomic(output, {'schemaVersion': '1.0', 'status': status, 'data': {'items': rows},
                        'page': {'complete': complete, 'nextCursor': next_cursor}, 'source': filters,
                        'profile': cloud.profile, 'skill_dir': str(cloud.root), 'source_command': source, 'error': error})
    for _ in range(max_pages):
        params = {**filters, **({'cursor': cursor} if cursor else {})}
        last = cloud.call('files', source, params)
        if last['status'] not in ('SUCCESS', 'EMPTY'):
            break
        page_rows = []
        items = (last.get('data') or {}).get('items', [])
        # Fetch one detail at a time: info reissues refs, and does not provide
        # an input index suitable for safely associating batched responses.
        for item in items:
            if not item.get('fileRef'):
                continue
            parent_path = (last.get('data') or {}).get('path')
            name = item.get('name')
            if (source == 'list' and not filters.get('recursive') and isinstance(parent_path, list)
                    and isinstance(name, str) and name and '/' not in name and name not in ('.', '..')):
                # The nonrecursive list contract binds every child to this directory.
                # Preserve the returned fileRef instead of paying an info request per image.
                page_rows.append({**item, 'path': parent_path + [name], 'ref_observed_at': now()})
                continue
            info = cloud.call('files', 'info', {'fileIds': [item['fileRef']], 'fields': ['name', 'size', 'time', 'location']})
            details = (info.get('data') or {}).get('items', [])
            if info['status'] != 'SUCCESS' or len(details) != 1:
                checkpoint('PARTIAL', cursor, info.get('error'))
                return {'status': 'PARTIAL', 'output': str(output), 'loaded': len(rows), 'blocked_by': info['status']}
            page_rows.append({**item, **details[0], 'ref_observed_at': now()})
        rows.extend(page_rows)
        page = last.get('page') or {}
        complete = page.get('complete') is True
        if complete:
            break
        cursor = page.get('nextCursor')
        if not cursor or cursor in visited:
            raise ValueError('incomplete provider page has missing/repeated cursor')
        visited.add(cursor)
        checkpoint('PARTIAL', cursor)
    status = 'SUCCESS' if complete else 'PARTIAL'
    checkpoint(status, None if complete else cursor, (last or {}).get('error'))
    return {'status': status, 'loaded': len(rows), 'complete': complete, 'output': str(output), 'provider_status': (last or {}).get('status')}


def download(cloud, batch, directory, output):
    from ..storage import atomic, records
    rows = records(batch)
    if not 1 <= len(rows) <= 100:
        raise ValueError('download batch must contain 1–100 members')
    cloud.capability('files.download')
    refs = [r['source_ref']['file_id'] for r in rows]
    destination = Path(directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    receipt = cloud.call('files', 'download', {'resources': refs, 'localDirectory': str(destination), 'conflictPolicy': 'fail'})
    mapped, seen = [], set()
    for item in (receipt.get('data') or {}).get('items', []):
        index = item.get('itemIndex')
        if type(index) is not int or not 0 <= index < len(rows) or index in seen:
            raise ValueError('download itemIndex cannot be mapped uniquely')
        seen.add(index)
        row = {'asset_id': rows[index]['asset_id'], 'status': 'error'}
        if item.get('status') == 'DOWNLOADED':
            path = (destination / item['localPath']).resolve()
            if not path.is_relative_to(destination) or not path.is_file():
                raise ValueError('download output missing or outside destination')
            row.update(status='downloaded', local_path=str(path))
        mapped.append(row)
    for index, row in enumerate(rows):
        if index not in seen:
            mapped.append({'asset_id': row['asset_id'], 'status': 'error'})
    # Runner-compatible JSONL; no credentials, download URLs or tokens.
    from ..manifest import write_manifest
    write_manifest(Path(output), mapped)
    return {'status': receipt['status'], 'counts': receipt.get('counts'), 'error': receipt.get('error'), 'output': str(output)}
