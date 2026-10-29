import { ThemeProvider, createTheme } from '@mui/material/styles'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import LoadingSkull from './components/LoadingSkull'
import './index.css'

// Material UI components follow the system light/dark setting, like the rest
// of the app (which uses `color-scheme: light dark`).
const theme = createTheme({ colorSchemes: { light: true, dark: true } })

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider theme={theme} defaultMode="system">
      <App />
      <LoadingSkull />
    </ThemeProvider>
  </StrictMode>,
)
