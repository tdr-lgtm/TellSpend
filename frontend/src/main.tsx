import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import ServerWakeBanner from "./components/ServerWakeBanner";
import ToastProvider from "./components/ToastProvider";
import { getHealth } from "./lib/api";
import "./index.css";

const queryClient = new QueryClient();

// Start waking the server (it sleeps when idle on the free host) as soon
// as the page opens, while the user is still reading or typing.
getHealth().catch(() => undefined);

// The outer error boundary is the last resort: whatever breaks, the user
// gets a message and a way to recover, never a blank white page.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary label="TellSpend">
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ServerWakeBanner />
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
