type NotesBoxProps = {
  value: string;
  onChange: (value: string) => void;
};

export default function NotesBox({ value, onChange }: NotesBoxProps) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Add notes for this day..."
      className="w-full min-h-24 rounded bg-gray-900 border border-gray-700 p-3"
    />
  );
}