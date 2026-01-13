"use client";
import { Server } from 'lucide-react';
import dynamic from 'next/dynamic';

// Dynamically import TraceMap to avoid SSR issues with Leaflet
const TraceMap = dynamic(() => import('./components/TraceMap'), { ssr: false });
import { useState } from "react";

type Hop = {
  hop: number;
  ip: string;
  hostname: string;
  latency: string;
  geo: {
    city: string;
    country: string;
    lat?: number;
    lon?: number;
  };
};

export default function Page() {
  const [target, setTarget] = useState("");
  const [probe, setProbe] = useState("icmp"); // icmp or tcp
  const [loading, setLoading] = useState(false);
  const [hops, setHops] = useState<Hop[]>([]);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    setHops([]);

    try {
      const endpoint = "/api/traceroute";
      const fetchOptions: RequestInit = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, mode: probe }),
      };
      const res = await fetch(endpoint, fetchOptions);
      if (!res.ok) {
        let msg = "Unknown error";
        try {
          const errData = await res.json();
          msg = errData.error || msg;
        } catch {}
        throw new Error(msg);
      }
      const data = await res.json();
      const hopsData = Array.isArray(data)
        ? data
        : (data && typeof data === "object" && Array.isArray((data as any).hops))
          ? (data as any).hops
          : null;

      if (hopsData !== null) {
        setHops(hopsData);
      } else {
        setError("Invalid response from traceroute server.");
        setHops([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setHops([]);
    }
    setLoading(false);
  };

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Traceroute Visualizer</h1>
      <div className="mb-2 flex items-center space-x-4">
        <div>
          <label htmlFor="probe-select" className="mr-2 font-medium">Probe:</label>
          <select
            id="probe-select"
            value={probe}
            onChange={(e) => setProbe(e.target.value)}
            className="border p-1 rounded"
          >
            <option value="icmp">ICMP (recommended)</option>
            <option value="tcp">TCP (port 80)</option>
          </select>
        </div>
        <div className="text-xs text-gray-600">Backend: configured via BACKEND_URL (.env.local)</div>
      </div>
      <textarea
        className="border w-full p-2 mb-2"
        rows={3}
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        placeholder="Enter a hostname or IP (e.g. google.com)"
      />
      <button
        onClick={handleSubmit}
        className="bg-blue-600 text-white px-4 py-2 rounded"
        disabled={loading}
      >
        {loading ? "Running traceroute..." : "Visualize"}
      </button>

      {error && <p className="text-red-600 mt-4">{error}</p>}

      {hops.length > 0 ? (
        <>
          <div className="mt-6">
            <h2 className="text-lg font-semibold mb-4">Route:</h2>
            <div className="flex overflow-x-auto space-x-4 pb-4">
              {hops.map((hop, idx) => (
                <div key={idx} className="flex items-center space-x-2">
                  <div className="flex flex-col items-center">
                    <div className="relative group">
                      <Server className="text-blue-600 w-6 h-6 mb-1 cursor-pointer" />
                      <div className="absolute z-10 hidden group-hover:block bg-black text-white text-xs rounded px-2 py-1 bottom-full mb-1 whitespace-nowrap shadow-md transition-opacity duration-200 opacity-90">
                        {hop.hostname} ({hop.ip})
                      </div>
                    </div>
                    <div className="bg-white border border-gray-300 shadow-md rounded-lg px-4 py-2 text-center min-w-[180px]">
                      <div className="font-bold text-sm">Hop {hop.hop}</div>
                      <div className="text-gray-700 text-xs">{hop.hostname}</div>
                      <div className="text-gray-500 text-xs">{hop.ip}</div>
                      <div
                        className={`font-medium ${
                          hop.latency === '---' || hop.latency === '—'
                            ? 'text-red-500'
                            : !isNaN(parseFloat(hop.latency)) && parseFloat(hop.latency) > 100
                            ? 'text-red-600'
                            : !isNaN(parseFloat(hop.latency)) && parseFloat(hop.latency) > 20
                            ? 'text-yellow-600'
                            : !isNaN(parseFloat(hop.latency))
                            ? 'text-green-600'
                            : 'text-blue-600'
                        }`}
                      >
                        {hop.latency}
                      </div>
                      <div className="text-xs text-gray-500">{hop.geo.city}{hop.geo.city && hop.geo.country ? ', ' : ''}{hop.geo.country}</div>
                    </div>
                  </div>
                  {idx < hops.length - 1 && (
                    hops[idx + 1].latency === '---' || hops[idx + 1].latency === '—' ? (
                      <div className="w-10 border-t border-dashed border-gray-400 opacity-50 h-1 flex-shrink-0" />
                    ) : (
                      <div className="w-10 h-1 bg-gray-400 flex-shrink-0" />
                    )
                  )}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-8 h-[500px]">
            <TraceMap hops={hops} />
          </div>
        </>
      ) : (
        error === '' && !loading && (
          <div className="mt-6 text-gray-500">No hops to display.</div>
        )
      )}
    </div>
  );
}
