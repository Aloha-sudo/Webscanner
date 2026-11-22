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
  if ((scanType === 'custom' || scanType === 'udp_custom') && ports) {
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

// SMB reports are imported metadata. These requests never connect to the target.
export async function listSmbReports(scanId: number): Promise<import('../types/smb').SmbReport[]> {
  const {data} = await api.get(`/scans/${scanId}/smb`);
  return data;
}
export async function importSmbReport(scanId: number, form: FormData): Promise<import('../types/smb').SmbReport> {
  const {data} = await api.post(`/scans/${scanId}/smb`, form);
  return data;
}
export async function browseSmbReport(scanId: number, reportId: string, params: {share: string; parent: string; query: string; offset: number}): Promise<import('../types/smb').SmbPage> {
  const {data} = await api.get(`/scans/${scanId}/smb/${reportId}/entries`, {params});
  return data;
}
export async function startSmbScan(scanId: number, body: import('../types/smb').SmbStart): Promise<import('../types/smb').SmbJob> {
  const {data} = await api.post(`/scans/${scanId}/smb/jobs`, body);
  return data;
}
export async function getSmbJob(scanId: number): Promise<import('../types/smb').SmbJob|null> {
  const {data} = await api.get(`/scans/${scanId}/smb/jobs/current`);
  return data;
}
export async function cancelSmbScan(scanId: number, token: string): Promise<import('../types/smb').SmbJob> {
  const {data} = await api.post(`/scans/${scanId}/smb/jobs/${token}/cancel`);
  return data;
}
export async function openSmbSession(scanId:number,reportId:string,body:import('../types/smb').SmbStart):Promise<import('../types/smb').SmbSession> {
  return (await api.post(`/scans/${scanId}/smb/${reportId}/session`,body)).data;
}
export async function closeSmbSession(scanId:number,reportId:string,token:string):Promise<void> {
  await api.delete(reportId ? `/scans/${scanId}/smb/${reportId}/session` : `/scans/${scanId}/smb/sessions/current`,{headers:{Authorization:`Bearer ${token}`}});
}
export async function startSmbFileAction(scanId:number,reportId:string,token:string,body:{action:string;share:string;path:string;directory?:boolean;offset?:number;query?:string}):Promise<import('../types/smb').SmbFileAction> {
  return (await api.post(`/scans/${scanId}/smb/${reportId}/actions`,body,{headers:{Authorization:`Bearer ${token}`}})).data;
}
export async function getSmbFileAction(scanId:number,reportId:string,token:string,id:string):Promise<import('../types/smb').SmbFileAction> {
  return (await api.get(`/scans/${scanId}/smb/${reportId}/actions/${id}`,{headers:{Authorization:`Bearer ${token}`}})).data;
}
export async function downloadSmbFile(scanId:number,reportId:string,token:string,id:string):Promise<Blob> {
  return (await api.get(`/scans/${scanId}/smb/${reportId}/actions/${id}/download`,{headers:{Authorization:`Bearer ${token}`},responseType:'blob',timeout:120000})).data;
}

export async function deleteSmbReports(scanId:number,reportIds:string[]):Promise<{deleted:string[]}> {
  const {data}=await api.post(`/scans/${scanId}/smb/delete`,{report_ids:reportIds});
  return data;
}

export async function searchSmbFiles(scanId:number,query:string,offset=0):Promise<import('../types/smb').SmbSearchPage> {
  const {data}=await api.get(`/scans/${scanId}/smb/search`,{params:{query,offset}});
  return data;
}

export async function collectSmbFiles(scanId:number,reportId:string,token:string,targets:string):Promise<import('../types/smb').SmbJob> {
  const {data}=await api.post(`/scans/${scanId}/smb/${reportId}/collect`,{targets},{headers:{Authorization:`Bearer ${token}`}});
  return data;
}

export async function checkSmbAccess(scanId:number,reportId:string,token:string,targets:string):Promise<import('../types/smb').SmbJob> {
  const {data}=await api.post(`/scans/${scanId}/smb/${reportId}/check`,{targets},{headers:{Authorization:`Bearer ${token}`}});
  return data;
}

export interface SecretFinding {size?:number|null;source?:SecretSource;id?:string;host:string;report_id:string;share:string;path:string;name:string;rule:string;kind:string;severity:string;evidence:string;}
export interface SecretJob {max_depth?:number|null;time_limit?:number;limits?:SecretTuning;share_names?:string[];exclude_shares?:string[];source?:SecretSource;locations?:string[];ftp_tls?:boolean;targets?:string;phase?:string;engine?:string;fast?:boolean;id:string;scan_id:number;status:string;account:string|null;created_at:string;error?:string;choices:{report_id:string;share:string}[];stats:Record<string,number>;findings?:SecretFinding[];finding_count?:number;partial?:boolean;}
export async function listSecretJobs(scanId:number):Promise<SecretJob[]> {return (await api.get(`/scans/${scanId}/secrets`)).data;}
export async function getSecretJob(scanId:number,id:string):Promise<SecretJob> {return (await api.get(`/scans/${scanId}/secrets/${id}`)).data;}
export async function startSecretJob(scanId:number,token:string,choices:{report_id:string;share:string}[]):Promise<SecretJob> {return (await api.post(`/scans/${scanId}/secrets`,{choices},{headers:{Authorization:`Bearer ${token}`}})).data;}
export async function cancelSecretJob(scanId:number,id:string):Promise<SecretJob> {return (await api.post(`/scans/${scanId}/secrets/${id}/cancel`)).data;}
export async function deleteSecretJob(scanId:number,id:string):Promise<void> {await api.delete(`/scans/${scanId}/secrets/${id}`);}

export async function createSecretWorkspace(targets:string):Promise<{id:number;targets:string}> {return (await api.post('/secrets/workspaces',{targets})).data;}

export async function searchSecrets(options:import('../types/smb').SmbStart,fast:boolean,scan_id?:number,share_names:string[]=[],source:SecretSource='smb',ftp_tls=false,tuning:SecretTuning={}):Promise<{job:SecretJob;session:import('../types/smb').SmbSession}> {return (await api.post('/secrets/search',{...secretSourceBody(options,source,ftp_tls),...tuning,fast,share_names:source==='smb'?(tuning.share_names??share_names):[],...(scan_id?{scan_id}:{})})).data;}
export async function secretHistory():Promise<SecretJob[]> {return (await api.get('/secrets/history')).data;}
export async function secretFindings(scan:number,id:string,query:string,offset:number):Promise<{items:SecretFinding[];total:number}> {return (await api.get(`/scans/${scan}/secrets/${id}/findings`,{params:{query,offset}})).data;}
export async function secretFile(scan:number,id:string,token:string,finding_id:string,action:string):Promise<import('../types/smb').SmbFileAction> {return (await api.post(`/scans/${scan}/secrets/${id}/files`,{finding_id,action},{headers:{Authorization:`Bearer ${token}`}})).data;}
export async function secretFileStatus(scan:number,id:string,token:string,action:string):Promise<import('../types/smb').SmbFileAction> {return (await api.get(`/scans/${scan}/secrets/${id}/files/${action}`,{headers:{Authorization:`Bearer ${token}`}})).data;}
export async function secretFileDownload(scan:number,id:string,token:string,action:string):Promise<Blob> {return (await api.get(`/scans/${scan}/secrets/${id}/files/${action}/download`,{headers:{Authorization:`Bearer ${token}`},responseType:'blob'})).data;}
export async function connectSecrets(scan:number,options:import('../types/smb').SmbStart):Promise<import('../types/smb').SmbSession> {return (await api.post(`/scans/${scan}/secrets/connection`,options)).data;}


export type SecretSource='smb'|'ftp'|'local';
export function secretSourceBody(options:import('../types/smb').SmbStart,source:SecretSource='smb',ftp_tls=false){
 return source==='smb'?{source,options}:{source,locations:options.targets.split(/[\n;]+/).map(value=>value.trim()).filter(Boolean),...(source==='ftp'?{ftp_username:options.mode==='anonymous'?'':options.username,ftp_password:options.mode==='anonymous'?'':options.password,ftp_tls}:{})};
}
export async function connectSecretSource(scan:number,id:string,options:import('../types/smb').SmbStart,source:SecretSource,tls=false):Promise<import('../types/smb').SmbSession>{return (await api.post(`/scans/${scan}/secrets/${id}/connection`,secretSourceBody(options,source,tls))).data;}

export interface SecretTuning {max_depth?:number|null;time_limit?:number;max_file_mb?:number;read_mb?:number;total_read_mb?:number|null;max_reads?:number|null;threads?:number;share_names?:string[];exclude_shares?:string[];exclude_paths?:string[];}
