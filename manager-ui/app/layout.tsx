import './globals.css';
import Link from 'next/link';

const nav = ['dashboard', 'auth', 'tickets', 'handles', 'database', 'system', 'logs'];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 border-r border-slate-800 p-4">
            <h1 className="mb-3 text-sm font-semibold">Webscraper NOC Dashboard</h1>
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
