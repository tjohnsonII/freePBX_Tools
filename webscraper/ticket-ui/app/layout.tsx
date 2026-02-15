import "./globals.css";
import Link from "next/link";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header>
          <h1>Ticket History</h1>
          <nav><Link href="/">Handles</Link></nav>
        </header>
        {children}
      </body>
    </html>
  );
}
