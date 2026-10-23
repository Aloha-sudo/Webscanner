export function validLocalDateTime(value:string):boolean{
  return !value||(/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)&&Number.isFinite(new Date(value).getTime()));
}
