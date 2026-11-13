import { isRankedProgramme, request } from './api'
import type { RankedProgramme, RequirementResult, StudentProfile } from './types'

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
  status:
    | 'completed'
    | 'needs_verification'
    | 'limit_reached'
    | 'no_matches'
    | 'model_error'
    | 'ambiguous_match'
  model: 'qwen3:4b-instruct'
  evaluated_on: string
  steps: number
  tool_calls: number
  recommendations: RankedProgramme[]
  fallback_recommendations?: RankedProgramme[]
  fallback_reason?: string | null
  model_error?: 'unavailable' | 'timeout' | 'invalid_response' | 'busy' | null
  discovery_candidates?: RankedProgramme[]
  discovery_candidate_ids?: number[]
  discovery_scope?: 'catalogue' | 'named_target'
  name_resolution?: ProgrammeResolution | null
  model_explanations?: ModelExplanation[]
  message: string
  warnings: string[]
  tool_trace: AgentToolTrace[]
  disclaimer: string
}

export interface ProgrammeOption {
  scholarship_id: number
  scholarship_name: string
  official_source_url: string
  last_verified_at: string
}

export interface ProgrammeResolution {
  status: 'not_requested' | 'matched' | 'ambiguous' | 'not_found'
  query: string | null
  method: 'exact' | 'alias' | 'fuzzy' | null
  candidate_ids: number[]
  options: ProgrammeOption[]
  message: string
}

export interface ModelExplanation {
  scholarship_id: number
  requirements: RequirementResult[]
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
      'model_error',
      'ambiguous_match',
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
  const fallback = value.fallback_recommendations ?? []
  if (
    (value.fallback_recommendations !== undefined &&
      !Array.isArray(value.fallback_recommendations)) ||
    !Array.isArray(fallback) ||
    fallback.length > 3 ||
    !fallback.every(
      (item) =>
        isRankedProgramme(item) &&
        item.assessment.status === 'needs_verification',
    ) ||
    (value.fallback_reason !== undefined &&
      value.fallback_reason !== null &&
      !text(value.fallback_reason))
  )
    return false
  if (
    fallback.length > 0 &&
    (value.recommendations.length > 0 ||
      !['no_matches', 'limit_reached', 'model_error'].includes(value.status) ||
      !text(value.fallback_reason) ||
      !value.fallback_reason.trim())
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
  const fallbackIds = fallback.map((item) => item.assessment.scholarship_id)
  if (
    new Set(ids).size !== ids.length ||
    new Set(fallbackIds).size !== fallbackIds.length
  )
    return false
  if (
    value.model_error !== undefined &&
    value.model_error !== null &&
    (!text(value.model_error) ||
      !['unavailable', 'timeout', 'invalid_response', 'busy'].includes(
        value.model_error,
      ))
  )
    return false
  if (
    (value.status === 'model_error') !== Boolean(value.model_error) ||
    (value.status === 'model_error' && value.recommendations.length > 0)
  )
    return false
  if (!discovery(value, value.recommendations)) return false
  if (!nameResolution(value, value.recommendations)) return false
  return explanations(value.model_explanations, value.recommendations)
}

function programmeResolution(value: unknown): value is ProgrammeResolution {
  if (
    !object(value) ||
    !text(value.status) ||
    !['not_requested', 'matched', 'ambiguous', 'not_found'].includes(value.status) ||
    !(
      value.query === null ||
      (text(value.query) &&
        value.query.trim().length > 0 &&
        value.query.length <= 300)
    ) ||
    !(
      value.method === null ||
      (text(value.method) && ['exact', 'alias', 'fuzzy'].includes(value.method))
    ) ||
    !Array.isArray(value.candidate_ids) ||
    !value.candidate_ids.every((id) =>
      boundedInteger(id, 1, Number.MAX_SAFE_INTEGER),
    ) ||
    !Array.isArray(value.options) ||
    !text(value.message)
  )
    return false
  const ids = value.candidate_ids
  if (new Set(ids).size !== ids.length || ids.length !== value.options.length)
    return false
  if (
    !value.options.every(
      (option, index) =>
        object(option) &&
        option.scholarship_id === ids[index] &&
        text(option.scholarship_name) &&
        option.scholarship_name.trim().length > 0 &&
        option.scholarship_name.length <= 300 &&
        safeUrl(option.official_source_url) &&
        date(option.last_verified_at),
    )
  )
    return false
  if (value.status === 'not_requested' || value.status === 'not_found')
    return ids.length === 0 && value.method === null
  return (
    value.method !== null &&
    (value.status === 'matched'
      ? ids.length >= 1 && ids.length <= 3
      : ids.length >= 2)
  )
}

function nameResolution(
  value: JsonObject,
  recommendations: RankedProgramme[],
): boolean {
  const resolution = value.name_resolution
  if (resolution === undefined || resolution === null)
    return value.status !== 'ambiguous_match'
  if (!programmeResolution(resolution)) return false
  const candidates = value.discovery_candidates ?? []
  const ids = value.discovery_candidate_ids ?? []
  const fallback = value.fallback_recommendations ?? []
  if (resolution.status === 'ambiguous' || resolution.status === 'not_found')
    return (
      value.status ===
        (resolution.status === 'ambiguous' ? 'ambiguous_match' : 'no_matches') &&
      value.steps === 0 &&
      value.tool_calls === 0 &&
      recommendations.length === 0 &&
      Array.isArray(candidates) &&
      candidates.length === 0 &&
      Array.isArray(ids) &&
      ids.length === 0 &&
      Array.isArray(fallback) &&
      fallback.length === 0
    )
  if (value.status === 'ambiguous_match') return false
  if (resolution.status === 'not_requested') return true
  if (
    value.discovery_scope !== 'named_target' ||
    !Array.isArray(ids) ||
    ids.length !== resolution.candidate_ids.length ||
    ids.some((id) => !resolution.candidate_ids.includes(id)) ||
    !Array.isArray(candidates) ||
    candidates.length !== resolution.options.length
  )
    return false
  return candidates.every((candidate) => {
    if (!isRankedProgramme(candidate)) return false
    const option = resolution.options.find(
      (item) => item.scholarship_id === candidate.assessment.scholarship_id,
    )
    return (
      option !== undefined &&
      option.scholarship_name === candidate.assessment.scholarship_name &&
      option.official_source_url === candidate.assessment.official_source_url &&
      option.last_verified_at === candidate.assessment.last_verified_at
    )
  })
}

function discovery(
  value: JsonObject,
  recommendations: RankedProgramme[],
): boolean {
  const hasDiscovery = [
    value.discovery_candidates,
    value.discovery_candidate_ids,
    value.discovery_scope,
  ].some((field) => field !== undefined)
  if (!hasDiscovery) return true
  if (
    !Array.isArray(value.discovery_candidates) ||
    value.discovery_candidates.length > 3 ||
    !value.discovery_candidates.every(isRankedProgramme) ||
    !Array.isArray(value.discovery_candidate_ids) ||
    !value.discovery_candidate_ids.every((id) =>
      boundedInteger(id, 1, Number.MAX_SAFE_INTEGER),
    ) ||
    !text(value.discovery_scope) ||
    !['catalogue', 'named_target'].includes(value.discovery_scope)
  )
    return false
  const ids = value.discovery_candidate_ids
  const visibleIds = value.discovery_candidates.map(
    (item) => item.assessment.scholarship_id,
  )
  if (
    new Set(ids).size !== ids.length ||
    new Set(visibleIds).size !== visibleIds.length ||
    visibleIds.some((id) => !ids.includes(id))
  )
    return false
  for (const candidate of value.discovery_candidates) {
    const selected = recommendations.find(
      (item) =>
        item.assessment.scholarship_id === candidate.assessment.scholarship_id,
    )
    if (!selected) continue
    const actual = candidate.assessment
    const model = selected.assessment
    if (
      actual.status !== model.status ||
      actual.admission_status !== model.admission_status ||
      actual.funding_status !== model.funding_status ||
      actual.application_status !== model.application_status ||
      actual.official_source_url !== model.official_source_url ||
      actual.last_verified_at !== model.last_verified_at ||
      actual.requirements.length !== model.requirements.length ||
      actual.requirements.some(
        (requirement) =>
          !model.requirements.some((item) => sameRequirement(requirement, item)),
      )
    )
      return false
  }
  if (value.discovery_scope === 'named_target')
    return recommendations.every((item) =>
      ids.includes(item.assessment.scholarship_id),
    )
  return value.discovery_candidates.every(
    (item) => item.assessment.status !== 'ineligible',
  )
}

function sameRequirement(original: RequirementResult, value: unknown): boolean {
  return (
    object(value) &&
    original.requirement === value.requirement &&
    original.scope === value.scope &&
    original.status === value.status &&
    original.explanation === value.explanation &&
    original.suggestion === value.suggestion
  )
}

function explanations(
  value: unknown,
  recommendations: RankedProgramme[],
): boolean {
  if (value === undefined) return true
  if (!Array.isArray(value) || value.length > 3) return false
  const seen = new Set<number>()
  for (const entry of value) {
    if (
      !object(entry) ||
      !boundedInteger(entry.scholarship_id, 1, Number.MAX_SAFE_INTEGER) ||
      seen.has(entry.scholarship_id) ||
      !Array.isArray(entry.requirements) ||
      entry.requirements.length < 1 ||
      entry.requirements.length > 4
    )
      return false
    seen.add(entry.scholarship_id)
    const candidate = recommendations.find(
      (item) => item.assessment.scholarship_id === entry.scholarship_id,
    )
    if (!candidate) return false
    const requirements = new Set<string>()
    for (const selected of entry.requirements) {
      if (!object(selected) || !text(selected.requirement)) return false
      if (requirements.has(selected.requirement)) return false
      requirements.add(selected.requirement)
      const original = candidate.assessment.requirements.find(
        (item) => item.requirement === selected.requirement,
      )
      if (!original || !sameRequirement(original, selected)) return false
    }
  }
  return true
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
