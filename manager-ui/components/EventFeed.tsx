'use client';
import { useEffect, useState } from 'react';
import { getJson } from '@/lib/api';

export function EventFeed() {
  const [events, setEvents] = useState<any[]>([]);
  useEffect(() => { getJson<{events:any[]}>('/api/logs/recent').then((d)=>setEvents(d.events.slice(-10))); }, []);
  return <ul className="space-y-1 text-xs">{events.map((e, i) => <li key={i}>{e.timestamp} {e.event_type} {e.message}</li>)}</ul>;
}
