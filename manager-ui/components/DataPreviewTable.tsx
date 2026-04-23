export function DataPreviewTable({ rows }: { rows: any[] }) {
  return <pre className="max-h-64 overflow-auto rounded bg-black p-2 text-xs">{JSON.stringify(rows, null, 2)}</pre>;
}
