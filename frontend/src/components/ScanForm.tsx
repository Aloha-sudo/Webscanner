import { uiText, t } from '../i18n/core';
import { useProject } from '../context/ProjectContext';
import { useEffect, useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { speedLabel } from '../utils/format';
import { createScan, getSpeedProfiles, getPortProfiles, listScans } from '../api/client';
import type { SpeedProfiles, DnsOptions } from '../types';

interface ScanFormProps {
  onCreated: () => void;
}

const PROFILES = [
  {
    value: 'quick',
    get label() {
  return t("Быстрый");
},
    get hint() {
  return t("Базовые TCP-сервисы");
},
    detail: '21,22,23,25,53,80,88,110,111,135,139,143,389,443,445,464,636,993,995,1723,3268,3269,3306,3389,5900,5985,5986,8006,8080,8443,9389',
    get info() {
  return t("FTP, SSH, DNS, почта, веб, SMB, RDP, WinRM и базовые TCP-службы Active Directory. UDP и динамический диапазон RPC не проверяются.");
},
  },
  {
    value: 'top100',
    get label() {
  return t("Топ 100");
},
    get hint() {
  return t("100 популярных TCP-портов");
},
    get detail() {
  return t("100 TCP-портов с наибольшей частотой в nmap-services");
},
    get info() {
  return t("Для первой проверки сети. Меньше портов — меньше времени на сканирование.");
},
  },
  {
    value: 'top1000',
    get label() {
  return t("Топ 1000");
},
    get hint() {
  return t("Топ-1000 портов nmap");
},
    get detail() {
  return t("1000 популярных TCP-портов по частоте nmap-services");
},
    get info() {
  return t("Баланс скорости и покрытия.");
},
  },
  {
    value: 'web',
    get label() {
  return t("Веб-интерфейсы");
},
    get hint() {
  return t("~100 веб-портов");
},
    detail: '80,81,443,3000,5000,8000,8006,8008,8080,8081,8443,8888,9000,9090,10000,10250,...',
    get info() {
  return t("Только HTTP/HTTPS/прокси.");
},
  },
  {
    value: 'full',
    get label() {
  return t("Все порты");
},
    get hint() {
  return t("Все 1-65535");
},
    get detail() {
  return t("1-65535 (полное сканирование)");
},
    get info() {
  return t("Медленно (2-6 мин/хост). Максимум информации.");
},
  },
  {
    value: 'custom',
    get label() {
  return t("Свои порты");
},
    get hint() {
  return t("Свой список");
},
    detail: '22,80,443,8000-8100',
    get info() {
  return t("Свой список портов через запятую.");
},
  },
];

const SPEED_META: Record<string, { icon: string; tagline: string; info: string; color: string }> = {
  normal: {
    icon: '',
    get tagline() {
  return t("Надёжно и стабильно");
},
    get info() {
  return t("Медленные хосты, роутеры, интернет. Максимум точности, но дольше.");
},
    color: 'text-gray-300',
  },
  fast: {
    icon: '',
    get tagline() {
  return t("Повышенная параллельность");
},
    get info() {
  return t("Локальная сеть, известные цели. Компромисс скорости и точности.");
},
    color: 'text-cyan-300',
  },
  hard: {
    icon: '',
    get tagline() {
  return t("Высокая параллельность");
},
    get info() {
  return t("Своя сеть, быстрые хосты. Максимум скорости, риск пропустить медленные порты.");
},
    color: 'text-red-300',
  },
};

export default function ScanForm({ onCreated }: ScanFormProps) {
  const {selection,project,part,loading:catalogLoading,setLocked}=useProject();
  const [resolveNames,setResolveNames] = useState(true);
  const [dnsServer,setDnsServer] = useState('');
  const [dnsTransport,setDnsTransport] = useState<DnsOptions['transport']>('auto');
  const [excludeIps,setExcludeIps] = useState('');
  const [excludeHosts,setExcludeHosts] = useState('');
  const [excludePorts,setExcludePorts] = useState('');
  const [target, setTarget] = useState('');
  const [scanType, setScanType] = useState('quick');
  const [customPorts, setCustomPorts] = useState('');
  const [sourceHost,setSourceHost] = useState('');
  const [recentSources,setRecentSources] = useState<string[]>([]);
  const [speed, setSpeed] = useState('normal');
  const [portProfiles, setPortProfiles] = useState<Record<string, {ports:string; count:number|null}>>({});
  const [speedProfiles, setSpeedProfiles] = useState<SpeedProfiles | null>(null);

  useEffect(() => {
    getPortProfiles().then(setPortProfiles).catch(console.error);
    getSpeedProfiles().then(setSpeedProfiles).catch(console.error);
  }, []);
  useEffect(()=>{
    let active=true;
    setSourceHost('');
    setDnsServer('');setDnsTransport('auto');
    setRecentSources([]);
    listScans(0,50,{project_id:selection.projectId,network_part_id:selection.partId}).then(({scans})=>{
      if(active)setRecentSources(Array.from(new Set(scans.filter(scan=>
        (scan.project_id??null)===selection.projectId&&(scan.network_part_id??null)===selection.partId
      ).map(scan=>scan.source_host?.trim()).filter((value):value is string=>!!value))));
    }).catch(()=>{});
    return()=>{active=false;};
  },[selection.projectId,selection.partId]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(()=>{setLocked(loading);return()=>setLocked(false);},[loading]);
  const isCustom = scanType === 'custom';
  const customInvalid = isCustom && !/^[\d,\-]+$/.test(customPorts);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!target.trim()) return;
    if(catalogLoading || (project&&!part)){setError(t("Выберите часть сети в верхней панели"));return;}
    if (isCustom && customInvalid) {
      setError(t("Порты: только цифры, запятые, дефисы (пример: 22,80,443,8000-8100)"));
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await createScan(
        target.trim(),
        scanType,
        isCustom ? customPorts : undefined,
        undefined,
        speed,
        {exclude_ips:excludeIps.trim() || undefined,exclude_hosts:excludeHosts.trim() || undefined,exclude_ports:excludePorts.trim() || undefined},
        {project_id:selection.projectId,network_part_id:selection.partId,source_host:sourceHost.trim()||undefined},
        {enabled:resolveNames,server:resolveNames?dnsServer.trim()||null:null,transport:dnsTransport},
      );
      setTarget('');
      setCustomPorts('');
      if(sourceHost.trim())setRecentSources(values=>Array.from(new Set([sourceHost.trim(),...values])));
      onCreated();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((item: {msg:string})=>item.msg).join('; ') : t("Ошибка при создании скана"));
    } finally {
      setLoading(false);
    }
  };

  return <form onSubmit={handleSubmit} className="scan-form scan-form-compact">
    <div className="compact-form-heading"><h2><Play size={18}/>{t("Новое сканирование")}</h2><span>{project?(part?`${project.name} / ${part.name}`:t("Выберите часть сети сверху")):t("Разовый скан без проекта")}</span></div>
    <div className="compact-scan-targets">
      <label htmlFor="new-scan-source">{t("Источник скана")}<input id="new-scan-source" type="text" list="recent-scan-sources" value={sourceHost} onChange={e=>setSourceHost(e.target.value)} maxLength={253} disabled={loading} placeholder={t("IP хоста, с которого сканируем")} aria-describedby="new-scan-source-help" autoComplete="off"/></label>
      <datalist id="recent-scan-sources">{recentSources.map(value=><option key={value} value={value}/>)}</datalist>
      <label htmlFor="new-scan-target">{t("Цель")}<input id="new-scan-target" type="text" aria-label={t("Цель сканирования")} value={target} onChange={e=>setTarget(e.target.value)} placeholder={t("192.168.1.0/24 или example.com")} disabled={loading}/></label>
    </div>
    <div className="compact-scan-settings">
      <label className="compact-port-field">{t("Порты")}<select aria-label={t("Профиль портов")} value={scanType} onChange={e=>setScanType(e.target.value)} disabled={loading}>{PROFILES.map(profile=><option key={profile.value} value={profile.value}>{profile.label}{portProfiles[profile.value]?.count?t(" · {v0} TCP-портов", {
  v0: portProfiles[profile.value].count
}):` · ${profile.hint}`}</option>)}</select></label>
      <fieldset className="compact-speed-field"><legend>{t("Скорость")}</legend><div className="compact-speed-options">{(['normal','fast','hard'] as const).map(value=><button key={value} type="button" disabled={loading} aria-pressed={speed===value} onClick={()=>setSpeed(value)}>{speed===value&&<span aria-hidden="true">✓</span>}{speedLabel(value)}</button>)}</div></fieldset>
      <button type="submit" className="compact-scan-submit" disabled={loading||catalogLoading|| (!!project&&!part)||!target.trim()||(isCustom&&customInvalid)}>{loading?<Loader2 size={16} className="animate-spin"/>:<Play size={16}/>} {loading?t("Запуск…"):t("Сканировать")}</button>
    </div>
    {isCustom&&<label className="compact-custom-ports">{t("Свои TCP-порты")}<input aria-label={t("Свои TCP-порты")} type="text" value={customPorts} onChange={e=>setCustomPorts(e.target.value)} placeholder="22,80,443,8000-8100" disabled={loading}/></label>}
    <p id="new-scan-source-help" className="compact-scan-help">{t("Источник необязателен. Перед запуском через другую точку доступа проверьте его IP.")}</p>
    <div className="compact-scan-details">
      <details className="scan-dns-disclosure"><summary>{t("Имена компьютеров ·")} {resolveNames ? (dnsServer.trim() || t("Автоматически")) : t("Выключено")}</summary><div className="scan-dns-settings">
      <label className="scan-dns-toggle"><input type="checkbox" checked={resolveNames} disabled={loading} onChange={event=>setResolveNames(event.target.checked)}/>{t("Найти имена компьютеров")}</label>
      {resolveNames&&<><label>{t("DNS-сервер")}<input aria-label={t("DNS-сервер нового скана")} value={dnsServer} onChange={event=>setDnsServer(event.target.value)} placeholder={t("Автоматически или IP сервера")} maxLength={45} disabled={loading}/></label><label>{t("Транспорт")}<select aria-label={t("Транспорт DNS нового скана")} value={dnsTransport} onChange={event=>setDnsTransport(event.target.value as DnsOptions['transport'])} disabled={loading}><option value="auto">{t("Авто: UDP → TCP")}</option><option value="tcp">{t("Только TCP")}</option><option value="udp">UDP</option></select></label><p>{t("Авто проверит сохранённый DNS части сети, найденные DNS-сервисы и системный DNS. До 60 секунд; получение имён можно повторить в карточке.")}</p></>}
    </div> </details>

      <details><summary>{t("Подробнее о профиле и скорости")}</summary><div className="compact-profile-details">{(()=>{const profile=PROFILES.find(item=>item.value===scanType)!;const configured=portProfiles[scanType];return <><h3>{profile.label} · {speedLabel(speed)}</h3><p>{profile.info}</p><p className="font-mono break-all">{configured?.ports&&configured.ports!=='dynamic'?configured.ports:profile.detail}</p><p>{SPEED_META[speed]?.info}</p>{speedProfiles?.[speed]&&<p>{t("Ожидание ответа:")} {Number(speedProfiles[speed].rustscan.timeout)/1000} {t("с")}</p>}</>;})()}</div></details>
      <details className="compact-exclusions"><summary>{t("Исключения")}{excludeIps||excludeHosts||excludePorts?t(" · настроены"):''}</summary><div className="compact-profile-details"><p>{t("Исключить из сканирования. Адреса, имена и порты указывайте через запятую или с новой строки.")}</p><div className="compact-exclusion-grid">
        <label>{t("IP и сети")}<textarea aria-label={t("Исключённые IP и сети")} disabled={loading} value={excludeIps} onChange={e=>setExcludeIps(e.target.value)} maxLength={4000} placeholder="192.168.1.10, 192.168.1.64/28"/></label>
        <label>{t("Имена хостов")}<textarea aria-label={t("Исключённые хосты")} disabled={loading} value={excludeHosts} onChange={e=>setExcludeHosts(e.target.value)} maxLength={4000} placeholder="printer.office.local"/></label>
        <label>{t("TCP-порты")}<textarea aria-label={t("Исключённые порты")} disabled={loading} value={excludePorts} onChange={e=>setExcludePorts(e.target.value)} maxLength={4000} placeholder="22, 9100, 8000-8100"/></label>
      </div><p>{t("Исключения сохраняются для следующего запуска. Имена разрешаются через DNS перед сканом; если разрешить имя не удалось, запуск отменяется.")}</p></div></details>
    </div>
    {error&&<div role="alert" className="report-alert mt-3">{uiText(error)}</div>}
  </form>;
}
