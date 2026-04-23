"use client";

type Props = {
  selectedHandle: string;
  search: string;
  handles: string[];
  onSearchChange: (next: string) => void;
  onSelect: (handle: string) => void;
};

export default function HandleDropdown({ selectedHandle, search, handles, onSearchChange, onSelect }: Props) {
  const list = Array.isArray(handles) ? handles : [];
  const filtered = (list ?? []).filter((h) => h.toLowerCase().includes(search.toLowerCase()));

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
