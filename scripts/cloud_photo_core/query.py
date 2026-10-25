"""Validated QuerySpec with three-valued AND/OR/NOT evaluation."""
import datetime as dt

GROUPS = {'file_metadata', 'thumbnail_tags', 'vision_tags', 'index_state'}
OPS = {'eq', 'contains', 'in', 'gte', 'lte', 'exists', 'between'}


def validate(spec, depth=0):
    if depth > 20 or not isinstance(spec, dict) or not spec:
        raise ValueError('invalid/too deep QuerySpec')
    logical = set(spec) & {'all', 'any', 'not'}
    if logical:
        if len(spec) != 1:
            raise ValueError('logical query must contain one operator')
        key = next(iter(logical))
        children = [spec[key]] if key == 'not' else spec[key]
        if not isinstance(children, list) or not children:
            raise ValueError('logical children must be nonempty')
        for child in children:
            validate(child, depth + 1)
    else:
        if set(spec) != {'field', 'op', 'value'}:
            raise ValueError('predicate requires field, op, value')
        if not isinstance(spec['field'], str) or spec['field'].count('.') != 1 or spec['field'].split('.')[0] not in GROUPS:
            raise ValueError('field must address a supported label group')
        if spec['op'] not in OPS:
            raise ValueError('unsupported predicate operator')
        value = spec['value']
        if spec['op'] == 'in' and (not isinstance(value, list) or not value):
            raise ValueError('in requires a nonempty array')
        if spec['op'] == 'between' and (not isinstance(value, list) or len(value) != 2):
            raise ValueError('between requires two inclusive bounds')
        if spec['op'] == 'exists' and not isinstance(value, bool):
            raise ValueError('exists requires a boolean')
    return spec


def field(record, name):
    group, key = name.split('.')
    value = record.get(group, {}).get(key)
    if value in (None, '', []):
        return None
    return value


def normalized(value):
    return value.casefold() if isinstance(value, str) else value


def comparable(value):
    if not isinstance(value, str):
        return value
    try:
        if len(value) == 14 and value.isdigit():
            return dt.datetime.strptime(value, '%Y%m%d%H%M%S')
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return value


def evaluate(record, spec):
    if 'not' in spec:
        result = evaluate(record, spec['not'])
        return None if result is None else not result
    for key in ('all', 'any'):
        if key in spec:
            values = [evaluate(record, child) for child in spec[key]]
            if key == 'all':
                return False if False in values else None if None in values else True
            return True if True in values else None if None in values else False
    value = field(record, spec['field'])
    op, wanted = spec['op'], spec['value']
    if op == 'exists':
        return (value is not None) == wanted
    if value is None:
        return None
    values = value if isinstance(value, list) else [value]
    if op == 'eq':
        return any(normalized(v) == normalized(wanted) for v in values)
    if op == 'contains':
        return any(isinstance(v, str) and isinstance(wanted, str) and wanted.casefold() in v.casefold() for v in values)
    if op == 'in':
        return any(normalized(v) in [normalized(w) for w in wanted] for v in values)
    try:
        a = comparable(value)
        if op == 'gte': return a >= comparable(wanted)
        if op == 'lte': return a <= comparable(wanted)
        return comparable(wanted[0]) <= a <= comparable(wanted[1])
    except (TypeError, ValueError):
        return None


def trace(record, spec):
    """Persist observed values and leaf decisions for review, not guessed reasons."""
    for key in ('all', 'any'):
        if key in spec:
            return {'operator': key, 'decision': evaluate(record, spec), 'children': [trace(record, c) for c in spec[key]]}
    if 'not' in spec:
        return {'operator': 'not', 'decision': evaluate(record, spec), 'child': trace(record, spec['not'])}
    return {'predicate': spec, 'observed': field(record, spec['field']), 'decision': evaluate(record, spec)}
