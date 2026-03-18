export function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card"><h2 className="mb-2 text-sm font-semibold">{title}</h2>{children}</section>;
}
