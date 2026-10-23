export interface DnsOptions { enabled: boolean; server?: string | null; transport: 'auto' | 'udp' | 'tcp'; }
export interface DnsEvidence { status: string; names: string[]; server?: string; transport?: string; checked_at?: string; method?: string; attempts?: DnsEvidence[]; }
export interface DnsSummary { counts?: Record<string,number>; servers?: {server:string;source:string;resolved:number;answered:number;statuses:string[]}[]; skipped?:number; budget_exceeded?:boolean; queued_at?:string; error?:string; }
export interface Scan {
  id: number;
  dns_options?: DnsOptions | null;
  dns_status?: string | null;
  dns_summary?: DnsSummary | null;
  retry_of_id?: number | null;
  target: string;
  project_id?:number|null; network_part_id?:number|null;
  project?: string | null; network?: string | null; source_host?: string | null; author?: string | null;
  observed_at?: string | null; scope_targets?: string | null; scope_ports?: string | null; scope_confirmed?: boolean;
  scan_type: string;
  ports?: string | null;
  comment?: string | null;
  speed?: string;
  exclude_ips?: string | null;
  exclude_hosts?: string | null;
  exclude_ports?: string | null;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage: string;
  total_hosts: number;
  total_ports: number;
  total_services: number;
  total_web: number;
  total_screenshots: number;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
}

export interface Service {
  id: number;
  url?: string | null;
  status_code?: number | null;
  title?: string | null;
  technologies?: string | null;
  ssl: boolean;
}

export interface Port {
  id: number;
  port: number;
  protocol: string;
  state: string;
  service?: string | null;
  version?: string | null;
  banner?: string | null;
  service_obj?: Service | null;
}

export interface Host {
  dns_result?: DnsEvidence | null;
  id: number;
  ip: string;
  hostname?: string | null;
  os?: string | null;
  ports: Port[];
}

export interface Screenshot {
  id: number;
  url: string;
  minio_path: string;
  status_code?: number | null;
  title?: string | null;
  technologies?: string | null;
}

export interface ScanDetail extends Scan {
  hosts: Host[];
  screenshots: Screenshot[];
}

export interface ScanListResponse {
  total: number;
  scans: Scan[];
}

export interface SpeedProfile {
  label: string;
  rustscan: { batch: string; timeout: string; tries: string; ulimit: string };
  nmap: { version: string; timing: string; host_timeout: string };
}

export type SpeedProfiles = Record<string, SpeedProfile>;
