import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-black text-white p-6 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">CCNA Lab Tracker</h1>
        <p className="text-gray-400 mb-6">
          90-day homelab execution tracker
        </p>
        <Link
          href="/tracker"
          className="inline-block rounded bg-blue-700 px-4 py-2 hover:bg-blue-600"
        >
          Open Tracker
        </Link>
      </div>
    </main>
  );
}