import "./globals.css";
import styles from "./layout.module.css";
import Link from "next/link";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={styles.body}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarBrand}>
            <div className={styles.sidebarBrandTitle}>123.NET<br />Webscraper</div>
            <div className={styles.sidebarBrandSub}>Hosted Dashboard</div>
          </div>
          <nav className={styles.nav}>
            <Link href="/" className={styles.navLink}>Dashboard</Link>
            <Link href="/vpbx" className={styles.navLink}>VPBX</Link>
            <Link href="/noc-queue" className={styles.navLink}>NOC Queue</Link>
            <Link href="/logs" className={styles.navLink}>Logs</Link>
          </nav>
        </aside>
        <div className={styles.content}>
          <header className={styles.header}>
            <span className={styles.headerTitle}>
              123.NET Webscraper
              <span className={styles.headerDot}>•</span>
              <span className={styles.envBadge}>Hosted</span>
              <span className={styles.headerDot}>•</span>
              <span className={styles.liveIndicator}>● Live</span>
            </span>
          </header>
          <div className={styles.main}>{children}</div>
        </div>
      </body>
    </html>
  );
}
