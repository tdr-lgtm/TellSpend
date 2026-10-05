/**
 * Routes. The home page needs a saved token; without one you are sent
 * to /login. Whether the token is still valid is checked by /auth/me.
 */

import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { getToken } from "./lib/token";
import Home from "./pages/Home";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import ResetPassword from "./pages/ResetPassword";
import Signup from "./pages/Signup";
import VerifyEmail from "./pages/VerifyEmail";
import AppLayout from "./components/AppLayout";

function RequireAuth({ children }: { children: ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  return (
     <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      {/* Opened from emails; they work signed in or not. */}
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />

      {/* The signed-in app is one page: expenses, people and balances. */}
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Home />} />
      </Route>

      {/* Anything else, including the old /contacts and /balances pages. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}