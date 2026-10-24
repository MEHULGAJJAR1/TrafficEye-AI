import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { TrafficProvider } from './store';
import './styles.css';

class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error('TrafficEye interface error', error, info); }
  render() {
    if (this.state.error) return <div className="boot-screen"><h1>TrafficEye could not render this view.</h1><p>Your saved backend data is safe. Reload the app; if the issue persists, capture the browser console error.</p><pre>{this.state.error.message}</pre><button className="btn primary" onClick={() => location.reload()}>Reload workspace</button></div>;
    return this.props.children;
  }
}
createRoot(document.getElementById('root')).render(<React.StrictMode><ErrorBoundary><TrafficProvider><App/></TrafficProvider></ErrorBoundary></React.StrictMode>);
