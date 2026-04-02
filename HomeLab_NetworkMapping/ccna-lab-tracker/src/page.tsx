import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-black text-white p-6 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">CCNA Lab Tracker</h1>
        <p className="text-gray-300 mb-6">
          Track your 90-day homelab and study plan.
        </p>
        <Link
          href="/tracker"
          className="inline-block px-4 py-2 rounded bg-blue-700 hover:bg-blue-600"
        >
          Open Tracker
        </Link>
      </div>
    </main>
  );
}