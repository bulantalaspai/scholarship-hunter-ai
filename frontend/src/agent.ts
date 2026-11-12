import { isRankedProgramme, request } from './api'
import type { RankedProgramme, StudentProfile } from './types'

export interface AgentToolTrace {
  step: number
  name: string
  status: 'ok' | 'invalid_arguments' | 'blocked' | 'error' | 'unknown_tool'
  arguments: Record<string, unknown>
  summary: string
  source_url: string | null
  fetched_at: string | null
}

export interface AgentResponse {
  status: 'completed' | 'needs_verification' | 'limit_reached' | 'no_matches'
  model: 'qwen3:4b-instruct'
  evaluated_on: string
  steps: number
  tool_calls: number
  recommendations: RankedProgramme[]
  message: string
  warnings: string[]
  tool_trace: AgentToolTrace[]
  disclaimer: string
}

type JsonObject = Record<string, unknown>
const object = (value: unknown): value is JsonObject =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown): value is string => typeof value === 'string'
const boundedInteger = (
  value: unknown,
  minimum: number,
  maximum: number,
): value is number =>
  typeof value === 'number' &&
  Number.isSafeInteger(value) &&
  value >= minimum &&
  value <= maximum

function date(value: unknown): value is string {
  if (!text(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return (
    !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  )
}

function safeUrl(value: unknown): value is string {
  if (!text(value)) return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password
  } catch {
    return false
  }
}

function trace(value: unknown): value is AgentToolTrace {
  return (
    object(value) &&
    boundedInteger(value.step, 1, 4) &&
    text(value.name) &&
    value.name.length <= 64 &&
    text(value.status) &&
    ['ok', 'invalid_arguments', 'blocked', 'error', 'unknown_tool'].includes(
      value.status,
    ) &&
    object(value.arguments) &&
    text(value.summary) &&
    (value.source_url === null || safeUrl(value.source_url)) &&
    (value.fetched_at === null ||
      (text(value.fetched_at) &&
        /^\d{4}-\d{2}-\d{2}T/.test(value.fetched_at) &&
        Number.isFinite(Date.parse(value.fetched_at))))
  )
}

function agentResponse(value: unknown): value is AgentResponse {
  if (
    !object(value) ||
    !text(value.status) ||
    ![
      'completed',
      'needs_verification',
      'limit_reached',
      'no_matches',
    ].includes(value.status) ||
    value.model !== 'qwen3:4b-instruct' ||
    !date(value.evaluated_on) ||
    !boundedInteger(value.steps, 0, 4) ||
    !boundedInteger(value.tool_calls, 0, 8) ||
    !Array.isArray(value.recommendations) ||
    value.recommendations.length > 3 ||
    !value.recommendations.every(isRankedProgramme) ||
    !text(value.message) ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every(text) ||
    !Array.isArray(value.tool_trace) ||
    !value.tool_trace.every(trace) ||
    !text(value.disclaimer)
  )
    return false
  if (
    value.tool_trace.length !== value.tool_calls ||
    value.tool_trace.some((item) => item.step > Number(value.steps))
  )
    return false
  const ids = value.recommendations.map(
    (item) => item.assessment.scholarship_id,
  )
  return new Set(ids).size === ids.length
}

export function fetchAgentRecommendations(
  profile: StudentProfile,
  goal: string,
  signal: AbortSignal,
): Promise<AgentResponse> {
  return request(
    '/api/agent/recommend',
    signal,
    agentResponse,
    { profile, goal },
    95_000,
  )
}
