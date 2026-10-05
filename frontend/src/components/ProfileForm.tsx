/**
 * Your profile: the name the assistant knows you by, and the currency new
 * expenses use when none is said. Below it, deleting the account (with
 * your password), which removes everything in it for good.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useMe } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { deleteMe, updateMe } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { clearToken } from "../lib/token";
import Button from "./Button";
import Field from "./Field";

export default function ProfileForm({ onDone }: { onDone: () => void }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(me.data?.name ?? "");
  const [currency, setCurrency] = useState(me.data?.default_currency ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const user = await updateMe({ name: name.trim(), default_currency: currency.trim().toUpperCase() });
      queryClient.setQueryData(["me"], user);
      toast({ message: "Profile saved" });
      onDone();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function removeAccount() {
    setBusy(true);
    setError(null);
    try {
      await deleteMe(password);
      clearToken();
      window.location.assign("/login");
    } catch (caught) {
      setError(caught);
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <Field label="Name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
        <Field
          label="Default currency"
          required
          minLength={3}
          maxLength={3}
          value={currency}
          onChange={(event) => setCurrency(event.target.value)}
        />
        <p className="-mt-2 text-xs text-slate-500">Used for new expenses. Saved ones keep their own currency.</p>
        <div className="flex justify-end">
          <Button type="submit" disabled={busy || !name.trim() || currency.trim().length !== 3}>
            Save
          </Button>
        </div>
      </form>

      <div className="rounded-2xl border border-rose-100 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-rose-400">Delete account</p>
        <p className="mt-1 text-xs text-slate-500">
          Removes your expenses, people and payments for good. Enter your password to confirm.
        </p>
        <div className="mt-2 flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <Field
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button variant="danger" onClick={removeAccount} disabled={busy || !password}>
            Delete
          </Button>
        </div>
      </div>

      {error != null && (
        <p role="alert" className="text-xs text-rose-700">
          {getErrorMessage(error)}
        </p>
      )}
    </div>
  );
}
