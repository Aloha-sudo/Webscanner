import { useSyncExternalStore } from 'react';
import { getLanguage, subscribeLanguage } from './i18n/core';
import { Routes, Route } from 'react-router-dom';
import TeamPage from './pages/TeamPage';
import Layout from './components/Layout';
import ReportsPage from './pages/ReportsPage';
import HomePage from './pages/HomePage';
import ScanDetailPage from './pages/ScanDetailPage';

function App() {
  useSyncExternalStore(subscribeLanguage,getLanguage,getLanguage);
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/scan/:id" element={<ScanDetailPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
