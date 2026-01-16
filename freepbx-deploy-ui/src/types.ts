export type Action =
  | 'deploy'
  | 'uninstall'
  | 'clean_deploy'
  | 'connect_only'
  | 'upload_only'
  | 'bundle'

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface JobInfo {
  id: string
  action: Action
  status: JobStatus
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  return_code?: number | null
  servers: string[]
}

export interface JobGetResponse {
  job: JobInfo
  tail: string[]
}
