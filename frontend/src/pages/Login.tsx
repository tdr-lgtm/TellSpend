
/**
 * Sign in with email and password.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import { Link, Navigate, useNavigate } from "react-router-dom";

import AuthLayout from "../components/AuthLayout";
import Button from "../components/Button";
import Field from "../components/Field";
import { errorBoxClass } from "../lib/styles";
import { login } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { getToken, saveToken } from "../lib/token";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const loginMutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (token) => {
      saveToken(token);
      navigate("/", { replace: true });
    },
    // Right password, email not verified yet: a code was sent; enter it.
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 403) {
        navigate(`/verify-email?email=${encodeURIComponent(email.trim().toLowerCase())}`);
      }
    },
  });

  // Already signed in: nothing to do here.
  if (getToken()) {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to see your spending."
      footer={
        <>
          New here?{" "}
          <Link to="/signup" className="font-medium text-slate-900 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          loginMutation.mutate();
        }}
      >
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <Link to="/forgot-password" className="-mt-2 self-end text-xs font-medium text-slate-500 hover:text-slate-900">
          Forgot password?
        </Link>

        {loginMutation.isError && (
          <p role="alert" className={errorBoxClass}>
            {getErrorMessage(loginMutation.error)}
          </p>
        )}

        <Button
          type="submit"
          disabled={loginMutation.isPending}
          className="mt-1 w-full"
          >
          {loginMutation.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}