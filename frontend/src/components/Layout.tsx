import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/history", label: "Post History", end: false },
  { to: "/settings", label: "Settings", end: false },
];

export default function Layout() {
  const { username, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white shadow-sm" style={{ background: "linear-gradient(135deg, var(--color-brand-500), var(--color-brand-700))" }}>
                LP
              </span>
              <span className="text-base font-semibold tracking-tight text-slate-900">PostPilot AI</span>
            </div>
            <nav className="flex gap-1" aria-label="Main">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span className="hidden sm:inline">{username}</span>
            <button onClick={() => void logout()} className="btn-secondary !py-1.5 !text-xs">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
