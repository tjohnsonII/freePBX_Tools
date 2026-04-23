/**
 * callflowTransform.ts
 *
 * Transforms a freepbx_dump.py JSON snapshot into a graph of nodes and edges
 * that can be rendered by @xyflow/react.
 *
 * Destination string format (from FreePBX / Asterisk dialplan):
 *   "timeconditions,<id>"          → Time Condition
 *   "ivr-<id>"                     → IVR menu
 *   "ext-group,<grpnum>"           → Ring Group
 *   "ext-queues,<id>"              → Queue
 *   "from-did-direct,<ext>"        → Direct to extension
 *   "ext-local,<vm-target>"        → Voicemail  (target like vmu101)
 *   "app-announcement-<id>"        → Announcement
 *   "play-system-recording,<id>"   → System Recording
 *   "directory"                    → Company Directory
 *   "ext-meetme,<room>"            → Conference Room
 *   "app-blackhole" / "hangup"     → Hang Up / Terminate
 */

// ── Dump JSON types ───────────────────────────────────────────────────────────

export type InboundRoute = {
  did: string
  cid: string
  destination: string
  label: string
}

export type RingGroup = {
  grpnum: string
  description: string
  grplist: string
  strategy: string
  ringtime: string
  postdest: string
}

export type Queue = {
  queue?: string
  queue_name?: string
  strategy?: string
  timeout?: string
  members?: string
  _dynamic_members?: unknown[]
}

export type IvrMenu = {
  ivr_id: string
  name: string
  announcement: string
}

export type IvrOption = {
  ivr_id: string
  selection: string
  dest: string
}

export type TimeCondition = {
  timeconditions_id: string
  displayname: string
  timegroupid: string
  true_dest: string
  false_dest: string
}

export type TimeGroup = {
  id: string
  timegroupid: string
  time: string
}

export type Announcement = {
  announcement_id: string
  description: string
  post_dest: string
}

export type Extension = {
  extension: string
  name: string
}

export type FreePBXDump = {
  inbound?: InboundRoute[]
  ringgroups?: RingGroup[]
  queues?: Queue[]
  ivrs?: { menus?: IvrMenu[]; options?: IvrOption[] }
  timeconditions?: TimeCondition[]
  timegroups?: TimeGroup[]
  announcements?: Announcement[]
  extensions?: Extension[]
  [key: string]: unknown
}

// ── Graph types ───────────────────────────────────────────────────────────────

export type CFNodeType =
  | 'did'
  | 'tc'
  | 'ivr'
  | 'ringgroup'
  | 'queue'
  | 'ext'
  | 'voicemail'
  | 'announce'
  | 'conference'
  | 'recording'
  | 'directory'
  | 'terminate'
  | 'loop'
  | 'unknown'

export type CFNode = {
  id: string
  nodeType: CFNodeType
  label: string
  detail: string
}

export type CFEdge = {
  id: string
  source: string
  target: string
  label: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseDest(dest: string): { ctx: string; rest: string[] } {
  const parts = dest.split(',')
  return { ctx: parts[0] ?? '', rest: parts.slice(1) }
}

function formatTimeRules(
  timegroupid: string,
  tgRules: Record<string, string[]>
): string {
  const rules = tgRules[timegroupid] ?? []
  if (!rules.length) return ''
  const pretty = rules.slice(0, 3).map((r) => {
    const [timeRange, , , dow] = r.split('|')
    const parts: string[] = []
    if (timeRange && timeRange !== '*') parts.push(timeRange)
    if (dow && dow !== '*') parts.push(`dow:${dow}`)
    return parts.join(' ') || r
  })
  return pretty.join('\n') + (rules.length > 3 ? `\n+${rules.length - 3} more` : '')
}

// ── Main transform ────────────────────────────────────────────────────────────

export function buildCallFlow(
  dump: FreePBXDump,
  did: string
): { nodes: CFNode[]; edges: CFEdge[] } {
  // ── lookup maps ──────────────────────────────────────────────────────────
  const tcById: Record<string, TimeCondition> = {}
  for (const tc of dump.timeconditions ?? []) tcById[tc.timeconditions_id] = tc

  const ivrMenus: Record<string, IvrMenu> = {}
  for (const m of dump.ivrs?.menus ?? []) ivrMenus[m.ivr_id] = m

  const ivrOptions: Record<string, IvrOption[]> = {}
  for (const o of dump.ivrs?.options ?? []) {
    if (!ivrOptions[o.ivr_id]) ivrOptions[o.ivr_id] = []
    ivrOptions[o.ivr_id].push(o)
  }

  const rgById: Record<string, RingGroup> = {}
  for (const rg of dump.ringgroups ?? []) rgById[rg.grpnum] = rg

  const queueById: Record<string, Queue> = {}
  for (const q of dump.queues ?? []) {
    if (q.queue) queueById[q.queue] = q
  }

  const extById: Record<string, string> = {}
  for (const e of dump.extensions ?? []) extById[e.extension] = e.name

  const annById: Record<string, Announcement> = {}
  for (const a of dump.announcements ?? []) annById[a.announcement_id] = a

  const tgRules: Record<string, string[]> = {}
  for (const tg of dump.timegroups ?? []) {
    if (!tgRules[tg.timegroupid]) tgRules[tg.timegroupid] = []
    if (tg.time) tgRules[tg.timegroupid].push(tg.time)
  }

  // ── graph state ──────────────────────────────────────────────────────────
  const nodeMap = new Map<string, CFNode>()
  const edges: CFEdge[] = []
  const edgeSet = new Set<string>()

  function addNode(id: string, node: CFNode): void {
    if (!nodeMap.has(id)) nodeMap.set(id, node)
  }

  function addEdge(source: string, target: string, label = ''): void {
    const eid = `${source}→${target}:${label}`
    if (!edgeSet.has(eid)) {
      edgeSet.add(eid)
      edges.push({ id: eid, source, target, label })
    }
  }

  // ── recursive resolver ───────────────────────────────────────────────────
  function resolve(
    dest: string,
    path: string[],
    parentId: string,
    edgeLabel = ''
  ): void {
    if (!dest) return

    // Loop detection
    if (path.includes(dest)) {
      const loopId = `loop:${dest}`
      addNode(loopId, {
        id: loopId,
        nodeType: 'loop',
        label: '⟳ Loop',
        detail: dest,
      })
      addEdge(parentId, loopId, edgeLabel)
      return
    }

    // Depth guard
    if (path.length > 20) {
      const stopId = `stop:${dest}:${parentId}`
      addNode(stopId, {
        id: stopId,
        nodeType: 'unknown',
        label: '…',
        detail: 'max depth',
      })
      addEdge(parentId, stopId, edgeLabel)
      return
    }

    const newPath = [...path, dest]
    const { ctx, rest } = parseDest(dest)

    // ── Time Condition ──────────────────────────────────────────────────
    if (ctx === 'timeconditions') {
      const tcId = rest[0] ?? ''
      const nodeId = `tc:${tcId}`
      const tc = tcById[tcId]
      const rules = tc ? formatTimeRules(tc.timegroupid, tgRules) : ''
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'tc',
        label: tc ? `⏱ ${tc.displayname}` : `⏱ TC ${tcId}`,
        detail: rules,
      })
      addEdge(parentId, nodeId, edgeLabel)
      if (tc?.true_dest) resolve(tc.true_dest, newPath, nodeId, 'TRUE')
      if (tc?.false_dest) resolve(tc.false_dest, newPath, nodeId, 'FALSE')
      return
    }

    // ── IVR ─────────────────────────────────────────────────────────────
    if (ctx.startsWith('ivr-')) {
      const ivrId = ctx.slice(4)
      const nodeId = `ivr:${ivrId}`
      const menu = ivrMenus[ivrId]
      const opts = ivrOptions[ivrId] ?? []
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'ivr',
        label: menu ? `🎛 ${menu.name}` : `🎛 IVR ${ivrId}`,
        detail: `${opts.length} option${opts.length !== 1 ? 's' : ''}`,
      })
      addEdge(parentId, nodeId, edgeLabel)
      // Only recurse if this node wasn't already in the graph (prevents double-expanding shared IVRs)
      if (!path.some((p) => p.startsWith(ctx))) {
        for (const opt of opts) {
          resolve(opt.dest, newPath, nodeId, opt.selection)
        }
      }
      return
    }

    // ── Ring Group ───────────────────────────────────────────────────────
    if (ctx === 'ext-group') {
      const grpnum = rest[0] ?? ''
      const nodeId = `rg:${grpnum}`
      const rg = rgById[grpnum]
      const memberCount =
        rg?.grplist?.split('-').filter((m) => m.trim()).length ?? 0
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'ringgroup',
        label: rg
          ? `🔔 ${rg.description || `Ring Group ${grpnum}`}`
          : `🔔 Ring Group ${grpnum}`,
        detail: rg
          ? `${rg.strategy} · ${memberCount} member${memberCount !== 1 ? 's' : ''}`
          : '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      if (rg?.postdest) resolve(rg.postdest, newPath, nodeId, 'post')
      return
    }

    // ── Queue ────────────────────────────────────────────────────────────
    if (ctx === 'ext-queues') {
      const qid = rest[0] ?? ''
      const nodeId = `q:${qid}`
      const q = queueById[qid]
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'queue',
        label: q?.queue_name ? `📋 ${q.queue_name}` : `📋 Queue ${qid}`,
        detail: q
          ? [q.strategy, q.timeout ? `${q.timeout}s` : '']
              .filter(Boolean)
              .join(' · ')
          : '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Direct to Extension ──────────────────────────────────────────────
    if (ctx === 'from-did-direct') {
      const ext = rest[0] ?? ''
      const nodeId = `ext:${ext}`
      const name = extById[ext]
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'ext',
        label: `👤 ${ext}${name ? ` — ${name}` : ''}`,
        detail: 'Extension',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Voicemail ────────────────────────────────────────────────────────
    if (ctx === 'ext-local') {
      const target = rest[0] ?? ''
      const nodeId = `vm:${target}`
      const m = target.match(/^vm([ubsi])(\d+)$/)
      if (m) {
        const [, code, ext] = m
        const suffix =
          ({ u: 'unavailable', b: 'busy', s: 'no msg', i: 'immediate' } as Record<
            string,
            string
          >)[code ?? ''] ?? code
        const name = extById[ext ?? '']
        addNode(nodeId, {
          id: nodeId,
          nodeType: 'voicemail',
          label: `📬 VM ${ext}${name ? ` — ${name}` : ''}`,
          detail: suffix ?? '',
        })
      } else {
        addNode(nodeId, {
          id: nodeId,
          nodeType: 'voicemail',
          label: `📬 ${target}`,
          detail: '',
        })
      }
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Announcement ─────────────────────────────────────────────────────
    if (ctx.startsWith('app-announcement-')) {
      const annId = ctx.split('-').pop() ?? ''
      const nodeId = `ann:${annId}`
      const ann = annById[annId]
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'announce',
        label: `📢 ${ann?.description || `Announcement ${annId}`}`,
        detail: '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      if (ann?.post_dest) resolve(ann.post_dest, newPath, nodeId, 'after')
      return
    }

    // ── System Recording ─────────────────────────────────────────────────
    if (ctx === 'play-system-recording') {
      const recId = rest[0] ?? ''
      const nodeId = `rec:${recId}`
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'recording',
        label: `🎵 Recording ${recId}`,
        detail: '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Company Directory ────────────────────────────────────────────────
    if (ctx === 'directory') {
      const nodeId = 'directory'
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'directory',
        label: '📖 Directory',
        detail: '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Conference Room ──────────────────────────────────────────────────
    if (ctx === 'ext-meetme') {
      const room = rest[0] ?? ''
      const nodeId = `conf:${room}`
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'conference',
        label: `👥 Conference ${room}`,
        detail: '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Hang Up / Blackhole ──────────────────────────────────────────────
    if (ctx === 'app-blackhole' || ctx === 'hangup') {
      const nodeId = 'terminate'
      addNode(nodeId, {
        id: nodeId,
        nodeType: 'terminate',
        label: '🔴 Hang Up',
        detail: '',
      })
      addEdge(parentId, nodeId, edgeLabel)
      return
    }

    // ── Unknown / Raw ────────────────────────────────────────────────────
    const nodeId = `unknown:${dest}`
    addNode(nodeId, {
      id: nodeId,
      nodeType: 'unknown',
      label: dest.length > 40 ? dest.slice(0, 40) + '…' : dest,
      detail: '',
    })
    addEdge(parentId, nodeId, edgeLabel)
  }

  // ── Entry point ──────────────────────────────────────────────────────────
  const route = (dump.inbound ?? []).find((r) => r.did === did)
  if (!route) return { nodes: [], edges: [] }

  const rootId = `did:${did}`
  addNode(rootId, {
    id: rootId,
    nodeType: 'did',
    label: `📞 ${did}`,
    detail: route.label || '',
  })

  if (route.destination) {
    resolve(route.destination, [], rootId, '')
  }

  return { nodes: Array.from(nodeMap.values()), edges }
}