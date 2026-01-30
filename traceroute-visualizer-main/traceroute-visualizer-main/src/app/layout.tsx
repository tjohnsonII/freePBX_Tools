import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "123NET Traceroute Visualizer",
  description: "123NET network diagnostics: traceroute visualization",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-96x96.png", type: "image/png", sizes: "96x96" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <header className="brandHeader">
          <a className="brandLogo" href="/" aria-label="123NET">
            <img src="/123net-logo.png" alt="123NET" />
          </a>
          <div className="brandHeaderText">
            <div className="brandAppName">Traceroute Visualizer</div>
            <div className="brandMeta">Network diagnostics</div>
          </div>
        </header>
        <main className="appContainer">{children}</main>
      </body>
    </html>
  );
}
