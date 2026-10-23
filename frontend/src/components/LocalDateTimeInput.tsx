import { t } from '../i18n/core';
import { validLocalDateTime } from '../utils/localDateTime';

/** Explicit HH:mm text field avoids OS-dependent AM/PM widgets. */
export default function LocalDateTimeInput({value,onChange,disabled,label}:{value:string;onChange:(value:string)=>void;disabled?:boolean;label:string}){
  const [date='',time='']=value.split('T');
  return <div className="local-date-time">
    <input type="date" aria-label={t('{v0}: дата',{v0:label})} value={date} disabled={disabled} onChange={event=>onChange(event.target.value?`${event.target.value}T${time||'00:00'}`:'')}/>
    <input type="text" inputMode="numeric" aria-label={t('{v0}: время, 24 часа',{v0:label})} aria-invalid={!validLocalDateTime(value)} title={t('Время от 00:00 до 23:59')} placeholder="HH:mm" maxLength={5} value={time} disabled={disabled||!date} onChange={event=>onChange(`${date}T${event.target.value}`)}/>
  </div>;
}
