"use client";

type Props = {
  handles: string[];
  selectedHandle: string;
  search: string;
  onSearchChange: (next: string) => void;
  onSelect: (handle: string) => void;
};

export default function HandleDropdown({ handles, selectedHandle, search, onSearchChange, onSelect }: Props) {
  return (
    <section>
      <label>
        Search handles
        <input
          value={search}
          placeholder="Type to search handles..."
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </label>

      <label>
        Handle
        <select value={selectedHandle} onChange={(e) => onSelect(e.target.value)}>
          <option value="">Select a handle</option>
          {handles.map((handle) => (
            <option key={handle} value={handle}>
              {handle}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
