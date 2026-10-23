"""Localize application diagnostics; stored reports and user content stay untouched."""
import json
import re
from pathlib import Path

MESSAGES = json.loads(Path(__file__).with_name('api.en.json').read_text())
PATTERNS = []
for source, translated in MESSAGES.items():
    if '{v' not in source:
        continue
    names = re.findall(r'\{(v\d+)\}', source)
    pattern = re.escape(source)
    for name in names:
        pattern = pattern.replace(re.escape('{'+name+'}'), '(.*?)', 1)
    PATTERNS.append((re.compile('^'+pattern+'$', re.S), names, translated))


def english_requested(header):
    # Respect language preference and quality, rather than matching a substring.
    choices = []
    for index, part in enumerate(header.split(',')):
        language, *params = part.strip().lower().split(';')
        try:
            quality = float(next((p.strip()[2:] for p in params if p.strip().startswith('q=')), '1'))
        except ValueError:
            continue
        language = language.split('-')[0]
        if language in ('ru', 'en') and 0 < quality <= 1:
            choices.append((quality, -index, language))
    return bool(choices) and max(choices)[2] == 'en'


def translate_error(message):
    if not isinstance(message, str):
        return message
    if message in MESSAGES:
        return MESSAGES[message]
    if message.startswith('Value error, '):
        return 'Value error, ' + translate_error(message[13:])
    for pattern, names, translated in PATTERNS:
        match = pattern.fullmatch(message)
        if match:
            values = dict(zip(names, match.groups()))
            return re.sub(r'\{(v\d+)\}', lambda m: values.get(m[1], m[0]), translated)
    return message


def error_code(status):
    return {400: 'invalid_request', 404: 'not_found', 409: 'conflict',
            422: 'validation_error', 503: 'queue_unavailable'}.get(status, 'request_failed')


def add_error_code(response, status):
    payload = json.loads(response.body)
    payload['code'] = error_code(status)
    response.body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    response.headers['content-length'] = str(len(response.body))
    return response
