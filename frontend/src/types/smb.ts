export interface SmbReport {
  id: string; host: string; account: string | null; source: string | null; author: string | null;
  observed_at: string | null; imported_at: string; filename: string; sha256: string;
  format: string; coverage?: string; authentication?: string; limits?: string[]; auth_method?: string; status?: string; error?: string|null; partial?: boolean; server?: {dialect?: string; signing_required?: boolean|null; signing_source?: string; client_signing_required?: boolean; smb1_supported?: boolean|null; guest?: boolean; name?: string; domain?: string; os?: string}; shares: {name: string; files: number; type?:number; listing?: string; error?: string|null; remark?: string; read_status?: string; write_status?: string; access?: string[]; write_method?: string}[]; file_count: number; directory_count: number;
}
export interface SmbEntry {
  share: string; path: string; parent: string; name: string; kind: 'file' | 'directory';
  metadata: {size?: string; ctime_epoch?: string; mtime_epoch?: string; atime_epoch?: string; listing?: string|null; error?: string; reparse_point?: boolean};
}
export interface SmbPage { partial?:boolean; folder?: SmbEntry|null; items: SmbEntry[]; total: number; offset: number; limit: number; }
export interface SmbJob {
  browse_session?: SmbSession;
  id: string; status: 'queued'|'running'|'completed'|'partial'|'failed'|'cancelled';
  completed: number; phase?: string; skipped?: number; report_ids: string[]; current_host?: string|null; error?: string|null;
  options: {targets: string[]; mode: 'anonymous'|'credentials'; username: string; domain: string};
}
export interface SmbStart {
  targets: string; mode: 'anonymous'|'credentials'; credential_type: 'password'|'ntlm'|'kerberos'; aes_key: string; kdc_host: string; server_names: Record<string,string>; username: string; domain: string; password: string; nt_hash: string;
  browse_scope?:'scan'|'host'; spider: boolean; depth: number; max_entries: number; include_admin: boolean;
}
export interface SmbSession {token:string;expires_in:number;expires_at?:number;account:string|null;hosts?:string[];report_id?:string|null;}
export interface SmbFileAction {id:string; status:'queued'|'running'|'completed'|'failed'; action?:string; error?:string; result?: {items?:SmbEntry[]; total?:number; offset?:number; limit?:number; partial?:boolean; rights?:{right:string;status:string;error?:string}[]; checked_at?:string; filename?:string; size?:number; preview?:{supported:boolean;text?:string;truncated?:boolean;reason?:string}};}

export interface SmbSearchHit {host:string;entry:SmbEntry;sources:{report_id:string;account:string|null}[];}
export interface SmbSearchPage {items:SmbSearchHit[];total:number;offset:number;limit:number;partial:boolean;truncated:boolean;hosts:number;covered_hosts:number;}

export interface SmbExplorerLocation {path:string;offset:number;query:string;selected:SmbEntry|null;scrollTop:number;}
