/**
 * The frame around the signed-in app: a slim top bar with the logo and
 * the signed-in user, and the page below it.
 */

import { useState } from "react";
import { Outlet } from "react-router-dom";

import { useLogout, useMe } from "../hooks/useAuth";
import Avatar from "./Avatar";
import Button from "./Button";
import Logo from "./Logo";
import Modal from "./Modal";
import ProfileForm from "./ProfileForm";

export default function AppLayout() {
  const me = useMe();
  const logout = useLogout();
  const [editing, setEditing] = useState(false);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Logo />

          <div className="flex items-center gap-2">
            {me.data && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                aria-label="Your profile"
                className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-slate-100"
              >
                <Avatar name={me.data.name} size="sm" />
                <span className="hidden text-sm font-medium text-slate-700 sm:inline">{me.data.name}</span>
              </button>
            )}
            <Button variant="ghost" size="sm" onClick={logout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>

      {editing && (
        <Modal title="Your profile" onClose={() => setEditing(false)}>
          <ProfileForm onDone={() => setEditing(false)} />
        </Modal>
      )}
    </div>
  );
}
