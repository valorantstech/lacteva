"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type Me, getMe, logout } from "@/lib/api";

/**
 * Who am I, and how do I leave (PORTAL-001 / F-10, F-11).
 *
 * There was no sign-out control at all before this — the only way to end a
 * session was to clear `localStorage` by hand, and the nav's "Sign in" link
 * stayed there whether you were signed in or not. The token is now HttpOnly,
 * so the portal cannot answer "am I signed in?" by looking at storage: it
 * asks the platform, which is the only authority anyway.
 */
export function SessionControls() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((session) => !cancelled && setMe(session))
      .catch(() => !cancelled && setMe(null))
      .finally(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, []);

  // Render nothing until the answer is known, rather than flashing "Sign in"
  // at somebody who is already signed in.
  if (!checked) return <span className="ml-auto" />;

  if (!me) {
    return (
      <a className="ml-auto text-muted-foreground hover:text-foreground" href="/login">
        Sign in
      </a>
    );
  }

  return (
    <span className="ml-auto flex items-center gap-3">
      <span className="text-muted-foreground" title={me.user.email}>
        {me.user.full_name || me.user.email}
      </span>
      <button
        type="button"
        className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        onClick={async () => {
          await logout();
          setMe(null);
          router.push("/login");
          router.refresh();
        }}
      >
        Sign out
      </button>
    </span>
  );
}
