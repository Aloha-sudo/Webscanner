import { t, formatDateTime } from '../i18n/core';
import { useState } from 'react';
import { Server, Globe, Shield } from 'lucide-react';
import type { Host, Port } from '../types';

interface HostCardProps {
  host: Host;
  matchedPorts?: Port[];
}

export default function HostCard({ host, matchedPorts }: HostCardProps) {
  const [showAll, setShowAll] = useState(false);
  const filteredPorts = matchedPorts ?? host.ports;
  const ports = showAll ? host.ports : filteredPorts;
  const hiddenPorts = host.ports.length - filteredPorts.length;
  return (
    <div className="ui-surface border border-border rounded-xl overflow-hidden">
      {/* Host header */}
      <div className="px-5 py-3 ui-subtle border-b border-border flex flex-wrap items-center gap-3">
        <Server className="w-4 h-4 text-accent" />
        <span className="font-mono font-bold text-accent">{host.ip}</span>
        {host.hostname && (
          <span className="text-sm text-gray-500 font-mono">{host.hostname}</span>
        )}
        {host.dns_result && <details className="host-dns-evidence"><summary>{host.dns_result.status==='resolved' ? host.dns_result.names.join(', ') : ({no_record:t("Нет PTR-записи"),unreachable:t("DNS не ответил"),refused:t("DNS: запрос запрещён"),dns_error:t("Ошибка DNS"),budget_exceeded:t("Имя не проверено: лимит времени"),no_server:t("DNS не найден")} as Record<string,string>)[host.dns_result.status] || t("Имя не определено")}</summary><div><p>{t("Метод: PTR")}{host.dns_result.server?` · DNS ${host.dns_result.server}`:''}{host.dns_result.transport?` · ${host.dns_result.transport.toUpperCase()}`:''}</p>{host.dns_result.checked_at&&<p>{t("Проверено:")} {formatDateTime(host.dns_result.checked_at)}</p>}{host.dns_result.attempts?.map((attempt,index)=><p key={index}>{attempt.server} · {attempt.transport} · {({resolved:t("получено имя"),no_record:t("нет PTR"),unreachable:t("нет ответа"),refused:t("запрос запрещён"),dns_error:t("ошибка DNS")} as Record<string,string>)[attempt.status]||attempt.status}</p>)}</div></details>}
        {host.os && (
          <span className="text-xs text-gray-600 px-2 py-0.5 ui-subtle border border-border rounded">
            {host.os}
          </span>
        )}
      </div>

      {hiddenPorts > 0 && <div className="scan-host-port-context">
        <span>{showAll ? t("Все порты: {v0}", {
  v0: host.ports.length
}) : t("Подходящие порты: {v0} из {v1}", {
  v0: filteredPorts.length,
  v1: host.ports.length
})}</span>
        <button type="button" className="report-choice" aria-expanded={showAll} onClick={() => setShowAll(value => !value)}>{showAll ? t("Только подходящие") : t("Все порты хоста")}</button>
      </div>}
      {/* Ports */}
      {ports.length > 0 ? (
        <div className="divide-y divide-border/50">
          {ports.map((port) => (
            <div key={port.id} className="px-5 py-3 hover:ui-subtle transition">
              <div className="flex items-start gap-4">
                <div className="font-mono font-bold text-lg text-white min-w-[60px]">
                  {port.port}
                  <span className="text-xs text-gray-500 ml-1">/{port.protocol}</span>
                </div>

                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-300">{port.service || 'unknown'}</span>
                    {port.version && (
                      <span className="text-xs text-gray-500 font-mono">{port.version}</span>
                    )}
                  </div>

                  {port.banner && <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all ui-subtle p-2 rounded border border-border"><span className="block text-gray-500 mb-1">{t("Баннер")}</span>{port.banner}</pre>}
                  {port.service_obj && (
                    <div className="text-xs space-y-0.5">
                      {port.service_obj.url && (
                        <div className="flex items-center gap-1.5 text-gray-400">
                          <Globe className="w-3 h-3" />
                          <a
                            href={port.service_obj.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-accent hover:underline font-mono"
                          >
                            {port.service_obj.url}
                          </a>
                          {port.service_obj.status_code && (
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                port.service_obj.status_code < 300
                                  ? 'bg-accent/20 text-accent'
                                  : port.service_obj.status_code < 400
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-red-500/20 text-red-400'
                              }`}
                            >
                              {port.service_obj.status_code}
                            </span>
                          )}
                          {port.service_obj.ssl && (
                            <Shield className="w-3 h-3 text-accent" />
                          )}
                        </div>
                      )}

                      {port.service_obj.title && (
                        <div className="text-gray-500 italic">
                          {port.service_obj.title}
                        </div>
                      )}

                      {port.service_obj.technologies && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {parseTechnologies(port.service_obj.technologies).map((tech, i) => (
                            <span
                              key={i}
                              className="px-1.5 py-0.5 ui-subtle border border-border rounded text-[10px] text-gray-400 font-mono"
                            >
                              {tech}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="px-5 py-3 text-sm text-gray-500">{t("Открытых портов нет")}</div>
      )}
    </div>
  );
}

function parseTechnologies(techStr: string): string[] {
  try {
    const parsed = JSON.parse(techStr);
    if (Array.isArray(parsed)) return parsed.slice(0, 10);
  } catch {}
  return [];
}
