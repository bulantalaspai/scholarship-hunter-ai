// Contracts mirror the FastAPI response models; null means unknown, never waived.
export type FundingType = 'fully_funded' | 'partially_funded' | 'unknown'
export type EligibilityStatus = 'eligible' | 'ineligible' | 'needs_verification'
export type DegreeLevel =
  'high_school' | 'associate' | 'bachelor' | 'master' | 'doctorate' | 'other'
export type FundingPreference = 'fully_funded' | 'any_funding'

export interface Scholarship {
  id: number
  scholarship_name: string
  university_or_provider: string
  destination_country: string[] | null
  degree_level: string | null
  eligible_study_fields: string[] | null
  eligible_nationalities: string[] | null
  minimum_gpa: number | null
  gpa_scale: number | null
  minimum_ielts: number | null
  funding_type: FundingType
  tuition_coverage: string | null
  living_stipend: string | null
  application_deadline: string | null
  application_cycle: string | null
  official_source_url: string
  last_verified_at: string
  additional_requirements: string | null
  notes: string | null
}

export interface ScholarshipPage {
  items: Scholarship[]
  total: number
  page: number
  page_size: number
}

export interface ScholarshipFilters {
  country?: string
  field?: string
  funding_type?: FundingType
  page?: number
  page_size?: number
}

export interface StudentProfile {
  nationality: string
  degree_level: DegreeLevel
  degree_completed?: boolean | null
  field_of_study: string
  gpa?: number | null
  gpa_scale?: number | null
  ielts_overall?: number | null
  intended_start_year: number
  funding_preference: FundingPreference
}

export interface RequirementResult {
  requirement: string
  scope: 'admission' | 'funding' | 'application'
  status: 'met' | 'failed' | 'unknown'
  explanation: string
  suggestion: string | null
}

export interface EligibilityResult {
  scholarship_id: number
  scholarship_name: string
  status: EligibilityStatus
  admission_status: EligibilityStatus
  funding_status: EligibilityStatus
  application_status: EligibilityStatus
  requirements: RequirementResult[]
  matched_requirements: string[]
  failed_requirements: string[]
  unknown_requirements: string[]
  suggestions: string[]
  explanation: string
  official_source_url: string
  last_verified_at: string
  rule_source_urls: string[]
  rules_verified_at: string | null
  evaluated_on: string
  disclaimer: string
}

export interface RankedProgramme {
  assessment: EligibilityResult
  ranking_reasons: string[]
}

export interface MatchResult {
  eligible: RankedProgramme[]
  needs_verification: RankedProgramme[]
  ineligible: RankedProgramme[]
  counts: Record<EligibilityStatus, number>
  total: number
  page: number
  page_size: number
}
