import type { CandidateProfile, EditableProfile, Preferences, UserProfile } from "../types"

export const PROFILE_STORAGE_KEY = "copilot.candidateProfiles.v1"

function id() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `profile-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function str(v: unknown) {
  return typeof v === "string" ? v.trim() : ""
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => str(x)).filter(Boolean) : []
}

function listText(v: unknown) {
  return strList(v).join("\n")
}

function editableYears(v: unknown) {
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return str(v)
}

function splitEditableList(v: string): string[] {
  return v.split(/[\n,，、;；]+/).map((x) => x.trim()).filter(Boolean)
}

export function editableProfileFromUserProfile(profile?: UserProfile | null): EditableProfile {
  return {
    name: str(profile?.name),
    summary: str(profile?.summary),
    skills: listText(profile?.skills),
    experiences: listText(profile?.experiences),
    education: str(profile?.education),
    years_experience: editableYears(profile?.years_experience),
    preferred_roles: listText(profile?.preferred_roles),
  }
}

export function userProfileFromEditableProfile(editable: EditableProfile, base: UserProfile = {}): UserProfile {
  const yearsText = editable.years_experience.trim()
  const years = Number(yearsText)
  return {
    ...base,
    name: editable.name.trim(),
    summary: editable.summary.trim(),
    skills: splitEditableList(editable.skills),
    experiences: splitEditableList(editable.experiences),
    education: editable.education.trim(),
    years_experience: yearsText ? (Number.isFinite(years) ? years : yearsText) : null,
    preferred_roles: splitEditableList(editable.preferred_roles),
  }
}

export function profileDisplayName(profile?: UserProfile | null) {
  const name = str(profile?.name)
  if (name) return name
  const summary = str(profile?.summary)
  return summary ? summary.slice(0, 24) : "未命名 Profile"
}

export function profileSummary(profile?: UserProfile | null) {
  return str(profile?.summary) || "尚未取得履歷定位摘要"
}

export function profileSkills(profile?: UserProfile | null, limit = 6) {
  return strList(profile?.skills).slice(0, limit)
}

export function profileRoles(profile?: UserProfile | null, prefs?: Preferences) {
  const roles = strList(profile?.preferred_roles)
  const targets = prefs?.target_titles?.map((x) => x.trim()).filter(Boolean) || []
  return [...new Set([...targets, ...roles])].slice(0, 4)
}

export function makeCandidateProfile(
  profile: UserProfile,
  opts: {
    id?: string
    label?: string
    resumeLabel?: string
    preferences?: Preferences
    saved?: boolean
    createdAt?: string
    updatedAt?: string
  } = {},
): CandidateProfile {
  const now = new Date().toISOString()
  return {
    id: opts.id || id(),
    label: (opts.label || profileDisplayName(profile)).trim() || "未命名 Profile",
    profile,
    resumeLabel: opts.resumeLabel,
    preferences: opts.preferences,
    createdAt: opts.createdAt || now,
    updatedAt: opts.updatedAt || now,
    saved: opts.saved,
  }
}

function normalizeCandidate(raw: unknown): CandidateProfile | null {
  if (!raw || typeof raw !== "object") return null
  const r = raw as Partial<CandidateProfile>
  if (!r.profile || typeof r.profile !== "object") return null
  return makeCandidateProfile(r.profile as UserProfile, {
    id: str(r.id) || undefined,
    label: str(r.label) || profileDisplayName(r.profile as UserProfile),
    resumeLabel: str(r.resumeLabel) || undefined,
    preferences: r.preferences,
    createdAt: str(r.createdAt) || undefined,
    updatedAt: str(r.updatedAt) || undefined,
    saved: true,
  })
}

export function loadCandidateProfiles(storage: Storage = localStorage): CandidateProfile[] {
  try {
    const raw = storage.getItem(PROFILE_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeCandidate).filter(Boolean) as CandidateProfile[]
  } catch {
    return []
  }
}

export function saveCandidateProfiles(profiles: CandidateProfile[], storage: Storage = localStorage) {
  storage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profiles.map((p) => ({ ...p, saved: true }))))
}

export function upsertCandidateProfile(list: CandidateProfile[], next: CandidateProfile) {
  return [next, ...list.filter((p) => p.id !== next.id)]
}
