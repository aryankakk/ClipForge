'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useRouter } from 'next/navigation';

interface NavProps {
  displayName?: string;
  profileImageUrl?: string | null;
}

export default function Navigation({ displayName, profileImageUrl }: NavProps) {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    localStorage.clear();
    router.replace('/');
  };

  const links = [
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/clips', label: 'Clips' },
  ];

  return (
    <nav
      className="sticky top-0 z-50 border-b border-[var(--forge-border)] flex items-center justify-between px-6 h-14"
      style={{ background: 'rgba(10, 10, 12, 0.95)', backdropFilter: 'blur(12px)' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-6">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div
            className="w-7 h-7 flex items-center justify-center"
            style={{ background: 'var(--forge-accent)' }}
          >
            <span className="text-white font-bold text-sm">⚡</span>
          </div>
          <span className="font-extrabold text-sm tracking-tight">CLIPFORGE</span>
        </Link>

        <div className="flex gap-1">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className="mono text-xs px-3 py-1.5 transition-colors"
                style={{
                  color: active ? 'var(--forge-text)' : 'var(--forge-muted)',
                  background: active ? 'var(--forge-surface)' : 'transparent',
                  borderBottom: active ? '2px solid var(--forge-accent)' : '2px solid transparent',
                }}
              >
                {link.label.toUpperCase()}
              </Link>
            );
          })}
        </div>
      </div>

      {/* User */}
      <div className="flex items-center gap-4">
        {displayName && (
          <div className="flex items-center gap-2">
            {profileImageUrl ? (
              <img src={profileImageUrl} alt={displayName} className="w-6 h-6 rounded-full" />
            ) : (
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: 'var(--forge-accent)' }}
              >
                {displayName[0].toUpperCase()}
              </div>
            )}
            <span className="mono text-xs text-[var(--forge-muted)]">{displayName}</span>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="mono text-xs px-3 py-1 border border-[var(--forge-border)] text-[var(--forge-muted)] hover:text-[var(--forge-text)] transition-colors"
        >
          LOGOUT
        </button>
      </div>
    </nav>
  );
}
