/**
 * The step after signing up (or signing in before verifying): enter the
 * 6-digit code that was emailed. A right code signs you in. A new code
 * can be asked for, once a minute.
 *
 * /verify-email?email=you@example.com
 */

import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import AuthLayout from "../components/AuthLayout";
import Button from "../components/Button";
import CodeInput from "../components/CodeInput";
import { resendVerification, verifyEmail } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { errorBoxClass } from "../lib/styles";
import { saveToken } from "../lib/token";

// Seconds before another code can be asked for (the server's limit).
const RESEND_WAIT = 60;

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const email = params.get("email") ?? "";
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [wait, setWait] = useState(RESEND_WAIT);

  // Count down to when a new code can be asked for.
  useEffect(() => {
    if (wait <= 0) {
      return;
    }
    const timer = window.setTimeout(() => setWait((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

  const verify = useMutation({
    mutationFn: (typed: string) => verifyEmail(email, typed),
    onSuccess: (token) => {
      saveToken(token);
      navigate("/", { replace: true });
    },
    // A wrong code: clear the boxes to type it again.
    onError: () => setCode(""),
  });

  const resend = useMutation({
    mutationFn: () => resendVerification(email),
    onSuccess: () => {
      setWait(RESEND_WAIT);
      setCode("");
      verify.reset();
    },
  });

  if (!email) {
    return <Navigate to="/signup" replace />;
  }

  return (
    <AuthLayout
      title="Check your email"
      subtitle={`Enter the 6-digit code we sent to ${email}.`}
      footer={
        <Link to="/login" className="font-medium text-slate-900 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (code.length === 6) {
            verify.mutate(code);
          }
        }}
      >
        <CodeInput
          value={code}
          onChange={setCode}
          onComplete={(full) => verify.mutate(full)}
          disabled={verify.isPending}
        />

        {verify.isError && (
          <p role="alert" className={errorBoxClass}>
            {getErrorMessage(verify.error)}
          </p>
        )}
        {resend.isSuccess && !verify.isError && (
          <p role="status" className="text-sm text-slate-600">
            {resend.data}
          </p>
        )}
        {resend.isError && (
          <p role="alert" className={errorBoxClass}>
            {getErrorMessage(resend.error)}
          </p>
        )}

        <Button type="submit" disabled={code.length !== 6 || verify.isPending} className="w-full">
          {verify.isPending ? "Checking…" : "Verify and continue"}
        </Button>

        <p className="text-center text-sm text-slate-500">
          Didn't get it? Check spam, or{" "}
          {wait > 0 ? (
            <span>ask for a new code in {wait}s</span>
          ) : (
            <button
              type="button"
              onClick={() => resend.mutate()}
              disabled={resend.isPending}
              className="font-medium text-slate-900 hover:underline disabled:opacity-50"
            >
              {resend.isPending ? "sending…" : "send a new code"}
            </button>
          )}
          .
        </p>
      </form>
    </AuthLayout>
  );
}
