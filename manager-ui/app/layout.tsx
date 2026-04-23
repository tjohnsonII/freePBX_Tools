import './globals.css';
import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '123.NET Webscraper',
  icons: {
    icon: [
      { url: '/favicon.ico' },
      { url: '/favicon-96x96.png', sizes: '96x96', type: 'image/png' },
      { url: '/favicon.svg', type: 'image/svg+xml' },
    ],
    shortcut: '/favicon.ico',
    apple: [{ url: '/apple-touch-icon.png', sizes: '180x180' }],
  },
};

const nav: { href: string; label: string; }[] = [
  { href: '/dashboard',  label: 'Dashboard' },
  { href: '/services',   label: '⚡ Services' },
  { href: '/tickets',    label: 'Tickets' },
  { href: '/handles',    label: 'Handles' },
  { href: '/database',   label: 'Database' },
  { href: '/system',     label: 'System' },
  { href: '/logs',       label: 'Logs' },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 border-r border-slate-800 p-4">
            <h1 className="mb-1 text-sm font-semibold">123 Hosted Tools</h1>
            <p className="mb-3 text-xs text-slate-500">manager.123hostedtools.com</p>
            <nav className="space-y-0.5 text-sm">
              {nav.map(({ href, label }) => (
                <Link className="block rounded px-2 py-1.5 hover:bg-slate-800 transition-colors" key={href} href={href}>
                  {label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="flex-1 p-4">{children}</main>
        </div>
      </body>
    </html>
  );
}
