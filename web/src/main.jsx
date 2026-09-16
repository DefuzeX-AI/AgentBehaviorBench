import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { Provider } from 'react-redux';
import { suiteStore } from './suite/store.js';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode><Provider store={suiteStore}><App /></Provider></React.StrictMode>,
);
