export function PortTable({ ports }: { ports: any }) {
  return <table className="w-full text-xs"><tbody>{Object.entries(ports.targets || {}).map(([k, v]) => <tr key={k}><td>{k}</td><td>{String(v)}</td></tr>)}</tbody></table>;
}
