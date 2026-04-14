import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import Dagre from '@dagrejs/dagre'

import {
  buildCallFlow,
  type CFNode,
  type CFNodeType,
  type FreePBXDump,
} from './callflowTransform'

// ── Node colour palette (dark-theme) ─────────────────────────────────────────

const NODE_COLORS: Record<CFNodeType, { bg: string; border: string; text: string }> = {
  did:        { bg: '#1e3a5f', border: '#3b82f6', text: '#93c5fd' },
  tc:         { bg: '#431407', border: '#f97316', text: '#fed7aa' },
  ivr:        { bg: '#2e1065', border: '#a855f7', text: '#d8b4fe' },
  ringgroup:  { bg: '#052e16', border: '#22c55e', text: '#86efac' },
  queue:      { bg: '#083344', border: '#06b6d4', text: '#a5f3fc' },
  ext:        { bg: '#1e293b', border: '#64748b', text: '#cbd5e1' },
  voicemail:  { bg: '#1e1b4b', border: '#818cf8', text: '#c7d2fe' },
  announce:   { bg: '#082f49', border: '#38bdf8', text: '#bae6fd' },
  conference: { bg: '#431407', border: '#fb923c', text: '#fed7aa' },
  recording:  { bg: '#1c1917', border: '#78716c', text: '#d6d3d1' },
  directory:  { bg: '#1c1917', border: '#78716c', text: '#d6d3d1' },
  terminate:  { bg: '#450a0a', border: '#ef4444', text: '#fca5a5' },
  loop:       { bg: '#422006', border: '#f59e0b', text: '#fde68a' },
  unknown:    { bg: '#111827', border: '#374151', text: '#9ca3af' },
}

const NODE_W = 220
const NODE_H = 76

// ── Converters ────────────────────────────────────────────────────────────────

function cfNodeToRf(n: CFNode): Node {
  const col = NODE_COLORS[n.nodeType]
  return {
    id: n.id,
    position: { x: 0, y: 0 }, // dagre fills in real positions
    data: {
      nodeType: n.nodeType,
      label: (
        <div style={{ lineHeight: 1.35 }}>
          <div style={{ fontWeight: 600, color: col.text, fontSize: 12 }}>
            {n.label}
          </div>
          {n.detail && (
            <div
              style={{
                fontSize: 10,
                color: col.text,
                opacity: 0.7,
                marginTop: 3,
                whiteSpace: 'pre-line',
              }}
            >
              {n.detail}
            </div>
          )}
        </div>
      ),
    },
    style: {
      background: col.bg,
      border: `1.5px solid ${col.border}`,
      borderRadius: n.nodeType === 'tc' ? 6 : 10,
      padding: '8px 12px',
      width: NODE_W,
      minHeight: NODE_H,
      boxShadow: `0 0 10px ${col.border}40`,
    },
  }
}

function cfEdgeToRf(e: { id: string; source: string; target: string; label: string }): Edge {
  const isTrue = e.label === 'TRUE'
  const isFalse = e.label === 'FALSE'
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    labelStyle: { fill: '#94a3b8', fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fill: '#0f172a', fillOpacity: 0.88 },
    labelBgPadding: [4, 3],
    style: {
      stroke: isTrue ? '#22c55e' : isFalse ? '#ef4444' : '#475569',
      strokeWidth: 1.5,
    },
    type: 'smoothstep',
  }
}

// ── Dagre layout ──────────────────────────────────────────────────────────────

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (!nodes.length) return nodes
  const g = new Dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 90, nodesep: 55 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  Dagre.layout(g)
  return nodes.map((n) => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } }
  })
}

// ── Legend ────────────────────────────────────────────────────────────────────

const LEGEND_ITEMS: Array<{ type: CFNodeType; label: string }> = [
  { type: 'did',       label: 'DID / Inbound' },
  { type: 'tc',        label: 'Time Condition' },
  { type: 'ivr',       label: 'IVR' },
  { type: 'ringgroup', label: 'Ring Group' },
  { type: 'queue',     label: 'Queue' },
  { type: 'ext',       label: 'Extension' },
  { type: 'voicemail', label: 'Voicemail' },
  { type: 'announce',  label: 'Announcement' },
  { type: 'terminate', label: 'Hang Up' },
]

function Legend() {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px 14px',
        padding: '8px 12px',
        background: 'rgba(15,23,42,0.85)',
        borderRadius: 10,
        border: '1px solid rgba(148,163,184,0.15)',
        fontSize: 11,
      }}
    >
      {LEGEND_ITEMS.map(({ type, label }) => {
        const col = NODE_COLORS[type]
        return (
          <span
            key={type}
            style={{ display: 'flex', alignItems: 'center', gap: 5 }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 12,
                height: 12,
                borderRadius: type === 'tc' ? 2 : 4,
                background: col.bg,
                border: `1.5px solid ${col.border}`,
                flexShrink: 0,
              }}
            />
            <span style={{ color: '#94a3b8' }}>{label}</span>
          </span>
        )
      })}
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ color: '#22c55e', fontSize: 14, lineHeight: 1 }}>─</span>
        <span style={{ color: '#94a3b8' }}>TRUE</span>
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ color: '#ef4444', fontSize: 14, lineHeight: 1 }}>─</span>
        <span style={{ color: '#94a3b8' }}>FALSE</span>
      </span>
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CallFlowGraph({ dump }: { dump: FreePBXDump }) {
  const dids = useMemo(
    () => (dump.inbound ?? []).map((r) => ({ did: r.did, label: r.label })),
    [dump]
  )

  const [selectedDid, setSelectedDid] = useState<string>(dids[0]?.did ?? '')

  const { rfNodes, rfEdges } = useMemo(() => {
    if (!selectedDid) return { rfNodes: [], rfEdges: [] }
    const { nodes, edges } = buildCallFlow(dump, selectedDid)
    const rfN = nodes.map(cfNodeToRf)
    const rfE = edges.map(cfEdgeToRf)
    const laid = applyDagreLayout(rfN, rfE)
    return { rfNodes: laid, rfEdges: rfE }
  }, [dump, selectedDid])

  if (!dids.length) {
    return (
      <div style={{ color: '#94a3b8', padding: 12, fontSize: 13 }}>
        No inbound routes found in the dump.
      </div>
    )
  }

  return (
    <div className="diag-callflow-wrap">
      {/* Toolbar */}
      <div className="diag-callflow-toolbar">
        <label className="diag-label" htmlFor="cf-did-select">
          DID
        </label>
        <select
          id="cf-did-select"
          className="diag-tool-select"
          value={selectedDid}
          onChange={(e) => setSelectedDid(e.target.value)}
          title="Select DID to visualize"
          aria-label="Select DID to visualize"
        >
          {dids.map((d) => (
            <option key={d.did} value={d.did}>
              {d.did}
              {d.label ? ` — ${d.label}` : ''}
            </option>
          ))}
        </select>
        <span className="diag-callflow-stats">
          {rfNodes.length} node{rfNodes.length !== 1 ? 's' : ''} ·{' '}
          {rfEdges.length} edge{rfEdges.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Legend */}
      <Legend />

      {/* Canvas */}
      <div className="diag-callflow-canvas">
        {rfNodes.length === 0 ? (
          <div className="diag-callflow-empty">
            No call flow data for this DID.
          </div>
        ) : (
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnScroll
            zoomOnScroll
            minZoom={0.15}
            maxZoom={2.5}
            colorMode="dark"
          >
            <Background color="#1e293b" gap={20} />
            <Controls />
            <MiniMap
              nodeStrokeWidth={1.5}
              nodeColor={(n) => {
                const t = n.data?.nodeType as CFNodeType | undefined
                return NODE_COLORS[t ?? 'unknown']?.bg ?? '#1e293b'
              }}
              nodeStrokeColor={(n) => {
                const t = n.data?.nodeType as CFNodeType | undefined
                return NODE_COLORS[t ?? 'unknown']?.border ?? '#475569'
              }}
              maskColor="rgba(15,23,42,0.75)"
              style={{ background: '#0b1220' }}
            />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}