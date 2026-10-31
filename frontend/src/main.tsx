import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { showRenderRecovery } from './render_recovery';
import './styles.css';

const container=document.getElementById('root')!;
ReactDOM.createRoot(container,{
  onUncaughtError(error){
    // No profile, model text, stack, session or error values are persisted or
    // sent anywhere. The original saved records remain server-owned.
    console.error('CampMate could not display this page. Reload to recover.');
    showRenderRecovery(container,error);
  },
}).render(
  <React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>,
);
