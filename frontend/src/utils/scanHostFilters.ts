import { t } from '../i18n/core';
import type { Host, Port } from '../types';

export const HOSTS_PAGE_SIZE = 50;

export function parseHostPorts(value: string): { ports: Set<number>; error: string } {
  const tokens = value.trim().split(/[\s,;]+/).filter(Boolean);
  if (tokens.some(token => !/^\d+$/.test(token) || Number(token) < 1 || Number(token) > 65535)) {
    return { ports: new Set(), error: t("Укажите порты от 1 до 65535 через запятую, например: 80, 443.") };
  }
  return { ports: new Set(tokens.map(Number)), error: '' };
}

export function filterScanHosts(hosts: Host[], query: string, portsText: string, protocol: string) {
  const parsed = parseHostPorts(portsText);
  const needle = query.trim().toLowerCase();
  if (parsed.error) return { matches: [] as { host: Host; ports: Port[] }[], portCount: 0, error: parsed.error };
  const restrictPorts = parsed.ports.size > 0 || protocol !== '';
  const matches = hosts.flatMap(host => {
    const hostMatches = [host.ip, host.hostname, ...(host.dns_result?.names || [])].some(value => value?.toLowerCase().includes(needle));
    const ports = host.ports.filter(port => {
      if (parsed.ports.size && !parsed.ports.has(port.port)) return false;
      if (protocol && port.protocol.toLowerCase() !== protocol) return false;
      return !needle || hostMatches || [port.service, port.version].some(value => value?.toLowerCase().includes(needle));
    });
    // Keep imported host-only observations when no port condition is requested.
    if (ports.length || (!restrictPorts && (!needle || hostMatches))) return [{ host, ports }];
    return [];
  });
  return { matches, portCount: matches.reduce((sum, item) => sum + item.ports.length, 0), error: '' };
}

export function hostPage(value: string | null, total: number) {
  const pages = Math.max(1, Math.ceil(total / HOSTS_PAGE_SIZE));
  const requested = value && /^\d+$/.test(value) ? Number(value) : 1;
  return { page: Math.max(1, Math.min(pages, requested)), pages };
}
