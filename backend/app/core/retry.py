"""A repeat is a new run; timestamps and evidence from the old run never carry over."""
from app.schemas.scan import ScanCreate


def retry_payload(scan, overrides=None):
    fields = ('target', 'scan_type', 'ports', 'comment', 'speed',
              'exclude_ips', 'exclude_hosts', 'exclude_ports',
              'project_id', 'network_part_id', 'source_host', 'author', 'dns_options')
    values = {key: getattr(scan, key, None) for key in fields}
    # Scope is evidence about a past run, not a promise about the repeated run.
    values.update(observed_at=None, scope_targets=None, scope_ports=None, scope_confirmed=False)
    if overrides:
        values.update(overrides)
    return ScanCreate(**values)
