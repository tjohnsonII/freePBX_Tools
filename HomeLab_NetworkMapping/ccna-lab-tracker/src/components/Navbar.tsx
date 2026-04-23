import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="border-b border-gray-800 bg-black text-white">
      <div className="max-w-5xl mx-auto px-6 py-4 flex gap-6">
        <Link href="/">Home</Link>
        <Link href="/tracker">Tracker</Link>
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/today">Today</Link>
      </div>
    </nav>
  );
}