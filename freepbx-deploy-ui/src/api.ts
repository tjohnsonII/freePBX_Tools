import type { Action, JobGetResponse, JobInfo } from './types'

export interface CreateJobRequest {
  action: Action
  servers: string
  workers: number
  username: string
  password: string
  root_password: string
  bundle_name: string
}

export async function createJob(req: CreateJobRequest): Promise<JobInfo> {
  const r = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(`createJob failed: ${r.status}`)
  return r.json()
}

export async function getJob(jobId: string): Promise<JobGetResponse> {
  const r = await fetch(`/api/jobs/${jobId}`)
  if (!r.ok) throw new Error(`getJob failed: ${r.status}`)
  return r.json()
}

export async function cancelJob(jobId: string): Promise<void> {
  const r = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
  if (!r.ok) throw new Error(`cancelJob failed: ${r.status}`)
}

export async function listJobs(): Promise<JobInfo[]> {
  const r = await fetch('/api/jobs')
  if (!r.ok) throw new Error(`listJobs failed: ${r.status}`)
  return r.json()
}
