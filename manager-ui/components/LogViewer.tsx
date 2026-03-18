'use client';
import { useEffect, useState } from 'react';
import { EventItem } from '@/lib/types';

export function LogViewer() {
  const [events, setEvents] = useState<EventItem[]>([]);
  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.hostname}:8787/ws/events`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (e) => {
      const item = JSON.parse(e.data) as EventItem;
      setEvents((prev) => [...prev.slice(-200), item]);
    };
    return () => ws.close();
  }, []);
  return <pre className="h-64 overflow-auto rounded bg-black p-2 text-xs">{events.map((e) => `[${e.timestamp}] ${e.level} ${e.event_type} ${e.message}`).join('\n')}</pre>;
}
