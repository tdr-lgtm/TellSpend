/**
 * Choose a new password, from the emailed link (/reset-password?token=…).
 * Afterwards every earlier sign-in is signed out, so this one signs out
 * too and goes to the sign-in page.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import AuthLayout from "../components/AuthLayout";
import Button from "../components/Button";
import Field from "../components/Field";
import { resetPassword } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { errorBoxClass } from "../lib/styles";
import { clearToken } from "../lib/token";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [mismatch, setMismatch] = useState(false);

  const reset = useMutation({
    mutationFn: () => resetPassword(token, password),
    onSuccess: () => {
      // Old sign-ins no longer work; start clean.
      clearToken();
      queryClient.clear();
    },
  });

  const footer = (
    <Link to="/login" className="font-medium text-slate-900 hover:underline">
      Back to sign in
    </Link>
  );

  if (!token) {
    return (
      <AuthLayout title="Reset your password" subtitle="This link is missing its code." footer={footer}>
        <p className="text-sm text-slate-700">
          Open the link from the email again, or{" "}
          <Link to="/forgot-password" className="font-medium text-slate-900 hover:underline">
            ask for a new one
          </Link>
          .
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="At least 8 characters." footer={footer}>
      {reset.isSuccess ? (
        <div className="flex flex-col gap-4">
          <p role="status" className="text-sm text-slate-700">
            {reset.data}
          </p>
          <Button className="w-full" onClick={() => navigate("/login")}>
            Sign in
          </Button>
        </div>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            setMismatch(password !== again);
            if (password === again) {
              reset.mutate();
            }
          }}
        >
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Field
            label="New password again"
            type="password"
            autoComplete="new-password"
            required
            value={again}
            onChange={(event) => setAgain(event.target.value)}
          />

          {(mismatch || reset.isError) && (
            <p role="alert" className={errorBoxClass}>
              {mismatch ? "The two passwords aren't the same." : getErrorMessage(reset.error)}
            </p>
          )}

          {reset.isError && (
            <p className="text-sm text-slate-500">
              <Link to="/forgot-password" className="font-medium text-slate-900 hover:underline">
                Ask for a new link
              </Link>
            </p>
          )}

          <Button type="submit" disabled={reset.isPending} className="mt-1 w-full">
            {reset.isPending ? "Saving…" : "Change password"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
