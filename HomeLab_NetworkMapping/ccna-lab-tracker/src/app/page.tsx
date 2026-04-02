import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-black p-6 text-white">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold">CCNA Lab Tracker</h1>
        <p className="mb-6 text-gray-300">Track your homelab progress and study milestones.</p>
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
