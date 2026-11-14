"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DegradedBanner } from "./DegradedBanner";
import { api, type Schemas } from "@/lib/http";

const NAV = [
  ["/inbox", "Job inbox"],
  ["/pipeline", "Pipeline"],
  ["/messages", "Messages"],
  ["/runs", "Agent runs"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
] as const;
const PUBLIC = ["/login"];

type User = Schemas["UserOut"];
const UserCtx = createContext<User | null>(null);
export const useUser = () => useContext(UserCtx);

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    api.GET("/api/auth/me").then(({ data, response }) => {
      if (!alive) return;
      if (response.status === 401 || !data) {
        setUser(null);
        if (!PUBLIC.includes(path)) router.replace("/login");
      } else {
        setUser(data);
        if (!data.onboarded && path !== "/onboarding") router.replace("/onboarding");
        if (path === "/login") router.replace("/inbox");
      }
      setChecked(true);
    });
    return () => {
      alive = false;
    };
  }, [path, router]);

  if (PUBLIC.includes(path) || path === "/onboarding") {
    return (
      <UserCtx.Provider value={user}>
        <main id="main" style={{ margin: "0 auto", maxWidth: 760 }}>{children}</main>
      </UserCtx.Provider>
    );
  }
  return (
    <UserCtx.Provider value={user}>
      <a className="skip" href="#main">Skip to content</a>
      <div className="shell">
        <nav className="nav" aria-label="Main">
          <div className="brand"><span aria-hidden>◆</span> GigBid</div>
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} aria-current={path.startsWith(href) ? "page" : undefined}>{label}</Link>
          ))}
          <div className="foot">
            {user ? <>{user.display_name} · {user.persona_id.replace(/_/g, " ")}<br />
              <button className="small" style={{ marginTop: 6 }} onClick={async () => { await api.POST("/api/auth/logout"); router.replace("/login"); }}>
                Sign out</button></> : null}
          </div>
        </nav>
        <main id="main">
          <DegradedBanner />
          {checked && user ? children : <div className="skeleton" style={{ width: "40%" }} />}
        </main>
      </div>
    </UserCtx.Provider>
  );
}
