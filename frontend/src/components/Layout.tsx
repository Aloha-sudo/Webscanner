import { t, getLanguage, setLanguage } from '../i18n/core';
import ProjectPicker from './ProjectPicker';
import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Radar, ScanLine, Files, Sun, Moon, Network } from 'lucide-react';

export default function Layout({children}: {children: React.ReactNode}) {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  const switchTheme = (next: string) => {
    setTheme(next); document.documentElement.dataset.theme = next;
    try { localStorage.setItem('webscanner-theme', next); } catch {}
  };
  const isScanDetail=useLocation().pathname.startsWith('/scan/');
  return <div className="scanner-shell reference-shell">
    <header className="reference-header">
      <NavLink to="/" className="reference-brand"><Radar size={24}/><span>WebScanner</span></NavLink>
      <nav className="reference-nav" aria-label={t("Основное меню")}>
        <NavLink to="/" end className={({isActive}:{isActive:boolean})=>isActive||isScanDetail ? 'active' : ''}><ScanLine size={16}/>{t("Сканирование")}</NavLink>
        <NavLink to="/reports" className={({isActive}:{isActive:boolean})=>isActive ? 'active' : ''}><Files size={16}/>{t("Отчёты и сравнение")}</NavLink>
        <NavLink to="/team" className={({isActive}:{isActive:boolean})=>isActive ? 'active' : ''}><Network size={16}/>{t("Карта сети")}</NavLink>
      </nav>
      <div className="reference-preferences">
      <div className="language-switch" role="group" aria-label={t('Язык интерфейса')}>
        <button lang="ru" aria-pressed={getLanguage()==='ru'} onClick={()=>setLanguage('ru')} title="Русский">RU</button>
        <button lang="en" aria-pressed={getLanguage()==='en'} onClick={()=>setLanguage('en')} title="English">EN</button>
      </div>
      <div className="theme-switch" role="group" aria-label={t("Тема интерфейса")}>
        <button aria-pressed={theme==='light'} onClick={()=>switchTheme('light')} title={t("Светлая тема с изумрудными акцентами")}><Sun size={15}/><span>{t("Светлая")}</span></button>
        <button aria-pressed={theme==='dark'} onClick={()=>switchTheme('dark')} title={t("Тёмно-синяя тема с голубыми акцентами")}><Moon size={15}/><span>{t("Тёмная")}</span></button>
      </div>
      </div>
    </header>
    <ProjectPicker/>
    <main className="scanner-main reference-main">{children}</main>
  </div>;
}
