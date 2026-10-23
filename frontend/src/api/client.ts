import { installLocaleInterceptors } from '../i18n/api';
import axios from 'axios';
import type { Scan, ScanDetail, ScanListResponse, SpeedProfiles, DnsOptions } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

installLocaleInterceptors(api);

export async function createScan(
  target: string,
  scanType: string = 'quick',
  ports?: string,
  comment?: string,
  speed: string = 'normal',
  exclusions?: {exclude_ips?: string; exclude_hosts?: string; exclude_ports?: string},
  context?: {project_id:number|null; network_part_id:number|null; source_host?:string},
  dnsOptions?: DnsOptions,
): Promise<Scan> {
  const body: {
    dns_options?: DnsOptions;
    target: string;
    scan_type: string;
    ports?: string;
    comment?: string;
    speed?: string;
    project_id?:number|null; network_part_id?:number|null; source_host?:string;
    exclude_ips?: string; exclude_hosts?: string; exclude_ports?: string;
  } = {
    target,
    scan_type: scanType,
    speed,
    ...exclusions,
    ...context,
    dns_options: dnsOptions,
  };
  if (scanType === 'custom' && ports) {
    body.ports = ports;
  }
  if (comment && comment.trim()) {
    body.comment = comment.trim();
  }
  const { data } = await api.post<Scan>('/scans', body);
  return data;
}

export async function updateScanComment(id: number, comment: string): Promise<Scan> {
  const { data } = await api.patch<Scan>(`/scans/${id}`, { comment });
  return data;
}

export async function listScans(skip = 0, limit = 50, context?: {project_id?:number|null;network_part_id?:number|null}): Promise<ScanListResponse> {
  const { data } = await api.get<ScanListResponse>('/scans', {
    params: { skip, limit, ...context },
  });
  return data;
}

export async function getScan(id: number): Promise<ScanDetail> {
  const { data } = await api.get<ScanDetail>(`/scans/${id}`);
  return data;
}

export async function deleteScan(id: number): Promise<void> {
  await api.delete(`/scans/${id}`);
}

export async function cancelScan(id: number): Promise<void> {
  await api.post(`/scans/${id}/cancel`);
}

export async function getSpeedProfiles(): Promise<SpeedProfiles> {
  const { data } = await api.get<SpeedProfiles>('/scans/speed-profiles');
  return data;
}

export async function getPortProfiles(): Promise<Record<string, {ports: string; count: number | null}>> {
  const {data} = await api.get('/scans/port-profiles');
  return data;
}

export async function retryScan(id:number, overrides:Record<string,unknown>={}):Promise<Scan>{
  const {data}=await api.post<Scan>(`/scans/${id}/retry`,overrides);return data;
}
