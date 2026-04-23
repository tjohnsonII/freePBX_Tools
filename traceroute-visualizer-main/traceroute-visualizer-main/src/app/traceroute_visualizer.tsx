'use client';

import React, { useState } from "react";
// import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Router } from "lucide-react";
import { getTargetValidationError } from "./utils/targetValidation";

export default function TracerouteVisualizer() {
  const [input, setInput] = useState("");
  const [hops, setHops] = useState<{ hop: number; label: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleVisualize = async () => {
    const target = input.trim();
    const validationError = getTargetValidationError(target);
    if (validationError) {
      setError(validationError);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await fetch('/api/traceroute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      });
      setLoading(false);
      if (!response.ok) {
        const { error } = await response.json();
        setError(error || "Unknown error occurred.");
        setHops([]);
        return;
      }
      const data = await response.json();
      setHops(data.hops);
    } catch (err) {
      setLoading(false);
      setError("Traceroute failed. Check console for details.");
      setHops([]);
      console.error("Traceroute failed", err);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold">Traceroute Visualizer</h1>
      <label htmlFor="traceroute-input" className="block font-medium mb-2">
        Destination Hostname or IP
      </label>
      <p className="text-sm text-gray-500 mb-2">
        Traceroute will be run from <strong>192.168.50.1</strong>. Enter a target hostname or IP address below.
      </p>
      <textarea
        id="traceroute-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        className="w-full p-4 border rounded-md h-64 font-mono"
        placeholder="Enter a domain or IP to trace from 192.168.50.1"
      ></textarea>
      <Button onClick={handleVisualize} disabled={loading}>Visualize</Button>

      {loading && (
        <div className="text-center my-4">
          <span className="animate-spin mr-2">⚙️</span> Running traceroute...
        </div>
      )}

      {error && (
        <div className="text-red-500 my-2 text-center">
          ❌ {error}
        </div>
      )}

      {!loading && !error && hops.length === 0 && (
        <div className="text-gray-500 text-center mt-4">
          No hops found. The destination may be unreachable.
        </div>
      )}

      {hops.length > 0 && !loading && !error && (
        <div className="mt-6 flex items-center space-x-4 overflow-x-auto">
          {hops.map((hop, index) => (
            <React.Fragment key={index}>
              <div className="flex flex-col items-center min-w-[160px]">
                <Router className="h-10 w-10 text-blue-500" />
                <div className="text-sm text-center mt-1">Hop {hop.hop}</div>
                <div className="text-xs text-gray-600 text-center">{hop.label}</div>
              </div>
              {index < hops.length - 1 && (
                <div className="h-1 w-8 bg-gray-400 rounded-full"></div>
              )}
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
