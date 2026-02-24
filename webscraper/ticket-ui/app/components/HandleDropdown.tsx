"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";

type Props = {
  selectedHandle: string;
  search: string;
  onSearchChange: (next: string) => void;
  onSelect: (handle: string) => void;
};

export default function HandleDropdown({ selectedHandle, search, onSearchChange, onSelect }: Props) {
  const [handles, setHandles] = useState<string[]>([]);

  useEffect(() => {
    apiGet<{ items: string[] }>("/api/handles").then((r) => setHandles(r.items)).catch(() => setHandles([]));
  }, []);

  const filtered = handles.filter((h) => h.toLowerCase().includes(search.toLowerCase()));

  return (
    <section>
      <label>
        Search handles
        <input value={search} placeholder="Type to search handles..." onChange={(e) => onSearchChange(e.target.value)} />
      </label>

      <label>
        Handle
        <select value={selectedHandle} onChange={(e) => onSelect(e.target.value)}>
          <option value="">Select a handle</option>
          {filtered.map((handle) => (
            <option key={handle} value={handle}>
              {handle}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
