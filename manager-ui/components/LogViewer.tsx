'use client';
import { useEffect, useState } from 'react';
import { EventItem } from '@/lib/types';

export function LogViewer() {
  const [events, setEvents] = useState<EventItem[]>([]);
  useEffect(() => {
    const ws = new WebSocket('ws://127.0.0.1:8787/ws/events');
    ws.onmessage = (e) => {
      const item = JSON.parse(e.data) as EventItem;
      setEvents((prev) => [...prev.slice(-200), item]);
    };
    return () => ws.close();
  }, []);
  return <pre className="h-64 overflow-auto rounded bg-black p-2 text-xs">{events.map((e) => `[${e.timestamp}] ${e.level} ${e.event_type} ${e.message}`).join('\n')}</pre>;
}
