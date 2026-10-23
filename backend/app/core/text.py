"""Make untrusted network text safe for PostgreSQL text columns."""

def database_text(value):
    return value.replace('\x00', '\\x00') if isinstance(value, str) else value


def error_text(error):
    message = str(error)
    safe = ''.join(f'\\x{ord(c):02x}' if ord(c) < 32 and c not in '\n\t' else c for c in message)
    return f'{type(error).__name__}: {safe}'[:4000]
