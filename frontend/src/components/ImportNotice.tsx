import { t } from '../i18n/core';
import { CheckCircle2, AlertTriangle, X } from 'lucide-react';

export default function ImportNotice({title,children,onClose,warning=false}: {title:string;children:React.ReactNode;onClose:()=>void;warning?:boolean}) {
  return <aside className="import-notice" role="status" aria-live="polite" aria-atomic="true">
    {warning ? <AlertTriangle size={22} className="text-yellow-400"/> : <CheckCircle2 size={22} className="import-notice-icon"/>}
    <div className="min-w-0"><h2 className="font-semibold text-sm">{title}</h2><div className="text-xs mt-2 space-y-2">{children}</div></div>
    <button aria-label={t("Закрыть уведомление о загрузке")} onClick={onClose} className="import-notice-close"><X size={16}/></button>
  </aside>;
}
