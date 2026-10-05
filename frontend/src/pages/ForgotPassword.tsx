/**
 * Ask for a password reset link. The answer is the same whether or not
 * the email has an account, so it never reveals who has one.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import AuthLayout from "../components/AuthLayout";
import Button from "../components/Button";
import Field from "../components/Field";
import { forgotPassword } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { errorBoxClass } from "../lib/styles";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");

  const request = useMutation({
    mutationFn: () => forgotPassword(email),
  });

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="We'll email you a link to choose a new one."
      footer={
        <Link to="/login" className="font-medium text-slate-900 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {request.isSuccess ? (
        <p role="status" className="text-sm text-slate-700">
          {request.data} The link works for a short while, once.
        </p>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            request.mutate();
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

          {request.isError && (
            <p role="alert" className={errorBoxClass}>
              {getErrorMessage(request.error)}
            </p>
          )}

          <Button type="submit" disabled={request.isPending} className="mt-1 w-full">
            {request.isPending ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
