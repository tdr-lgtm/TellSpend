/**
 * Ask for a password reset link. The server says plainly what happened:
 * no account with that email (offered a sign-up instead), the link sent,
 * one sent moments ago, or the email couldn't go out.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
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

  const noAccount = isAxiosError(request.error) && request.error.response?.status === 404;

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="We'll email you a link to choose a new one."
      footer={
        <Link to="/login" className="font-semibold text-emerald-700 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {request.isSuccess ? (
        <div role="status" className="flex flex-col gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="m3 7 9 6 9-6" />
            </svg>
          </div>
          <p className="text-sm leading-relaxed text-slate-700">{request.data}</p>
          <p className="text-xs text-slate-500">The link works once, for a short while.</p>
          <button
            type="button"
            onClick={() => request.reset()}
            className="self-start text-sm font-semibold text-emerald-700 hover:underline"
          >
            Use a different email
          </button>
        </div>
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
            onChange={(event) => {
              setEmail(event.target.value);
              if (request.isError) request.reset();
            }}
          />

          {request.isError && (
            <div role="alert" className={errorBoxClass}>
              {getErrorMessage(request.error)}
              {noAccount && (
                <>
                  {" "}
                  <Link to="/signup" className="font-semibold underline underline-offset-2">
                    Create an account
                  </Link>
                </>
              )}
            </div>
          )}

          <Button variant="brand" type="submit" disabled={request.isPending} className="mt-1 w-full">
            {request.isPending ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
