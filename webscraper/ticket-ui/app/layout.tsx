import "./globals.css";
import Link from "next/link";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header>
          <h1>123.NET Ticket Knowledge Base</h1>
          <nav><Link href="/">KB Dashboard</Link> | <Link href="/logs">Logs</Link></nav>
        </header>
        {children}
      </body>
    </html>
  );
}
