
/**
 * Create an account, then enter the 6-digit code emailed to verify it
 * (the next screen). Signing in only works once the email is verified.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "react-router-dom";

import AuthLayout from "../components/AuthLayout";
import Button from "../components/Button";
import Field from "../components/Field";
import SelectField from "../components/SelectField";
import { errorBoxClass } from "../lib/styles";
import { signup } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { getToken } from "../lib/token";

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];

export default function Signup() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [currency, setCurrency] = useState("INR");

  const signupMutation = useMutation({
    mutationFn: () => signup({ name, email, password, default_currency: currency }),
    // Next: the code that was emailed.
    onSuccess: (user) => navigate(`/verify-email?email=${encodeURIComponent(user.email)}`),
  });

  if (getToken()) {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Track what you spend and who owes whom."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-slate-900 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          signupMutation.mutate();
        }}
      >
        <Field
          label="Name"
          autoComplete="name"
          required
          maxLength={100}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />

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
          autoComplete="new-password"
          required
          minLength={8}
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        <SelectField
          label="Default currency"
          value={currency}
          onChange={(event) => setCurrency(event.target.value)}
          options={CURRENCIES.map((code) => ({ value: code, label: code }))}
        />

        {signupMutation.isError && (
          <p role="alert" className={errorBoxClass}>
            {getErrorMessage(signupMutation.error)}
          </p>
        )}

        <Button
          type="submit"
          disabled={signupMutation.isPending}
          className="mt-1 w-full"
          >
          {signupMutation.isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}