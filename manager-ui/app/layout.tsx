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

const nav = ['dashboard', 'tickets', 'handles', 'database', 'system', 'logs'];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 border-r border-slate-800 p-4">
            <h1 className="mb-3 text-sm font-semibold">Webscraper Hosted Dashboard</h1>
            <nav className="space-y-1 text-sm">
              {nav.map((item) => (
                <Link className="block rounded px-2 py-1 hover:bg-slate-800" key={item} href={`/${item}`}>
                  {item[0].toUpperCase() + item.slice(1)}
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
