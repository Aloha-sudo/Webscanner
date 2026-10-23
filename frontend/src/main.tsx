import axios from 'axios';
import { installLocaleInterceptors } from './i18n/api';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import App from './App';
import './index.css';

installLocaleInterceptors(axios);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ProjectProvider><App /></ProjectProvider>
    </BrowserRouter>
  </React.StrictMode>
);
