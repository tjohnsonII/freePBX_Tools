// main.tsx - Entry point for the React application
// This file initializes the React app and renders the root component (App) into the DOM.

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css' // Global styles
import App from './App.tsx' // Main app component

// Create a root and render the App component inside React.StrictMode for highlighting potential problems
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
