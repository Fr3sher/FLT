import { Component } from 'react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Log in production too: staying silent outside DEV left no diagnostics for full-screen
    // crashes. Send the message, stack and component stack to the browser console so the exact
    // cause can be traced, such as a component reading an undefined field.
    try {
      console.error(
        '[ErrorBoundary]',
        error?.message || error,
        '\nstack:', error?.stack,
        '\ncomponentStack:', info?.componentStack,
      );
    } catch { /* never let logging itself break the fallback UI */ }
  }

  render() {
    if (this.state.hasError) {
      // Root-level boundary: full-screen recovery UI with a reload action so a
      // render crash never leaves the user staring at a blank white page.
      if (this.props.showReload) {
        return (
          <div
            className="min-h-screen flex flex-col items-center justify-center gap-4 p-6 text-center bg-app text-content"
            role="alert"
          >
            <p className="text-lg font-semibold">
              {this.props.fallbackMessage || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="py-2.5 px-5 rounded-lg bg-gradient-primary text-gray-950 text-sm font-semibold cursor-pointer hover:-translate-y-px transition-transform"
            >
              Reload the page
            </button>
          </div>
        );
      }
      // Inline boundary (e.g. a single widget): compact fallback.
      return (
        <div className="text-center py-8 text-content-muted" role="alert">
          <p>{this.props.fallbackMessage || 'Something went wrong. Please refresh the page.'}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
