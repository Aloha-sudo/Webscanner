import { t } from '../i18n/core';
import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

export default function WorkspaceDialog({open,title,busy=false,wide=false,onClose,children}:{open:boolean;title:string;busy?:boolean;wide?:boolean;onClose:()=>void;children:React.ReactNode}){
  const dialog=useRef<HTMLDialogElement>(null);const heading=useId();
  useEffect(()=>{const element=dialog.current;if(!element)return;if(open&&!element.open)element.showModal();if(!open&&element.open)element.close();},[open]);
  return <dialog ref={dialog} className={`workspace-dialog ${wide?'workspace-dialog-wide':''}`} aria-labelledby={heading} onCancel={event=>{if(busy)event.preventDefault();else onClose();}} onClick={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
    <header><h2 id={heading}>{title}</h2><button type="button" disabled={busy} aria-label={t("Закрыть: {v0}", {
  v0: title
})} onClick={onClose}><X size={18}/></button></header>
    <div className="workspace-dialog-content">{children}</div>
  </dialog>;
}
