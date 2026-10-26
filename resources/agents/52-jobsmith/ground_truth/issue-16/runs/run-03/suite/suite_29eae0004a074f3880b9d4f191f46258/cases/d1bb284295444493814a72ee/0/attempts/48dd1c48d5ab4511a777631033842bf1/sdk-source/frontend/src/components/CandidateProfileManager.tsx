import { useState } from "react"
import type { CandidateProfile, EditableProfile, Preferences, UserProfile } from "../types"
import {
  editableProfileFromUserProfile,
  profileDisplayName,
  profileRoles,
  profileSkills,
  profileSummary,
  userProfileFromEditableProfile,
} from "../lib/profiles"
import { Badge } from "../ui/Badge"
import { Button } from "../ui/Button"
import { Check, CheckCircle2, Pencil, Save, Trash2, UserRound, UsersRound, X } from "../ui/icons"

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" }) }
  catch { return iso }
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-sm text-slate-700 break-words">{value || "未設定"}</dd>
    </div>
  )
}

const fieldClass = "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200"

function EditField(
  { label, value, onChange, multiline = false, placeholder = "" }:
  { label: string; value: string; onChange: (value: string) => void; multiline?: boolean; placeholder?: string },
) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-500 mb-1">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className={`${fieldClass} resize-y`}
          placeholder={placeholder}
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={fieldClass}
          placeholder={placeholder}
        />
      )}
    </label>
  )
}

export function CandidateProfileManager(
  {
    profiles, activeProfile, preferences, onSelectProfile, onSaveActiveProfile,
    onUpdateActiveProfile, onDeleteProfile, onClearActiveProfile, compact = false,
  }: {
    profiles: CandidateProfile[]
    activeProfile: CandidateProfile | null
    preferences?: Preferences
    onSelectProfile: (p: CandidateProfile | null) => void
    onSaveActiveProfile?: (label?: string) => void | Promise<void>
    onUpdateActiveProfile?: (profile: UserProfile) => void
    onDeleteProfile?: (id: string) => void
    onClearActiveProfile?: () => void
    compact?: boolean
  },
) {
  const selectedId = profiles.some((p) => p.id === activeProfile?.id) ? activeProfile?.id : ""

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold flex items-center gap-2">
            <UserRound className="w-4 h-4 text-brand-600" />候選人 Profile
          </h3>
          <p className="text-sm text-slate-500">
            儲存後可跨 session 選用；重新開啟 App 不會自動套用，產出前仍需確認。
          </p>
        </div>
        {activeProfile && <Badge tone="brand">目前使用</Badge>}
      </div>

      {activeProfile ? (
        <ActiveProfileCard
          key={`${activeProfile.id}-${activeProfile.label}-${activeProfile.updatedAt}`}
          activeProfile={activeProfile}
          activeIsSaved={Boolean(activeProfile.saved && selectedId)}
          preferences={preferences}
          onSaveActiveProfile={onSaveActiveProfile}
          onUpdateActiveProfile={onUpdateActiveProfile}
          onClearActiveProfile={onClearActiveProfile}
        />
      ) : (
        <div className="border border-dashed border-slate-300 rounded-lg p-4 bg-slate-50 text-sm text-slate-600">
          目前未選 Profile。手動選擇已儲存 Profile，或先到「自動找職缺 / 履歷健檢」提供履歷。
        </div>
      )}

      {profiles.length > 0 && (
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700 flex items-center gap-1.5" htmlFor="candidate-profile-select">
            <UsersRound className="w-4 h-4 text-slate-400" />選擇已儲存 Profile
          </label>
          <select
            id="candidate-profile-select"
            value={selectedId}
            onChange={(e) => {
              const next = profiles.find((p) => p.id === e.target.value) || null
              onSelectProfile(next)
            }}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-200"
          >
            <option value="">不自動套用，請手動選擇</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
      )}

      {!compact && profiles.length > 0 && (
        <div className="space-y-2">
          {profiles.map((p) => (
            <div key={p.id} className="flex items-center gap-3 border border-slate-200 rounded-lg p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm text-slate-900 truncate">{p.label}</p>
                <p className="text-xs text-slate-500 truncate">{profileSummary(p.profile)}</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => onSelectProfile(p)}>使用</Button>
              {onDeleteProfile && (
                <button
                  type="button"
                  onClick={() => onDeleteProfile(p.id)}
                  aria-label={`刪除 ${p.label}`}
                  title="刪除 Profile"
                  className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ActiveProfileCard(
  {
    activeProfile, activeIsSaved, preferences, onSaveActiveProfile,
    onUpdateActiveProfile, onClearActiveProfile,
  }:
  {
    activeProfile: CandidateProfile
    activeIsSaved: boolean
    preferences?: Preferences
    onSaveActiveProfile?: (label?: string) => void | Promise<void>
    onUpdateActiveProfile?: (profile: UserProfile) => void
    onClearActiveProfile?: () => void
  },
) {
  const [label, setLabel] = useState(activeProfile.label || "")
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<EditableProfile>(() => editableProfileFromUserProfile(activeProfile.profile))
  const [saved, setSaved] = useState(false)
  const skills = profileSkills(activeProfile.profile, 6)
  const roles = profileRoles(activeProfile.profile, preferences)

  async function saveActive() {
    if (!onSaveActiveProfile) return
    await onSaveActiveProfile(label)
    setSaved(true)
  }

  function updateDraft(field: keyof EditableProfile, value: string) {
    setDraft((d) => ({ ...d, [field]: value }))
    setSaved(false)
  }

  function startEdit() {
    setDraft(editableProfileFromUserProfile(activeProfile.profile))
    setEditing(true)
    setSaved(false)
  }

  function applyEdit() {
    if (!onUpdateActiveProfile) return
    onUpdateActiveProfile(userProfileFromEditableProfile(draft, activeProfile.profile))
    setEditing(false)
  }

  return (
    <div className="border border-slate-200 rounded-lg p-4 bg-white">
      <div className="flex flex-wrap items-start gap-3 justify-between">
        <div className="min-w-0">
          <p className="font-medium text-slate-900 truncate">{profileDisplayName(activeProfile.profile)}</p>
          <p className="text-sm text-slate-600 mt-0.5">{profileSummary(activeProfile.profile)}</p>
        </div>
        {activeIsSaved && <span className="text-xs text-emerald-700 inline-flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5" />已儲存
        </span>}
      </div>
      {editing ? (
        <div className="mt-4 space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <EditField label="姓名" value={draft.name} onChange={(v) => updateDraft("name", v)} placeholder="例：王予辰" />
            <EditField label="年資" value={draft.years_experience} onChange={(v) => updateDraft("years_experience", v)} placeholder="例：3" />
          </div>
          <EditField
            label="定位摘要"
            value={draft.summary}
            onChange={(v) => updateDraft("summary", v)}
            multiline
            placeholder="例：AI / 前端工程師，熟悉 Codex、Claude Code、Vue、FastAPI"
          />
          <div className="grid sm:grid-cols-2 gap-3">
            <EditField
              label="技能（可用換行、頓號或逗號分隔）"
              value={draft.skills}
              onChange={(v) => updateDraft("skills", v)}
              multiline
            />
            <EditField
              label="目標職稱（可用換行、頓號或逗號分隔）"
              value={draft.preferred_roles}
              onChange={(v) => updateDraft("preferred_roles", v)}
              multiline
            />
          </div>
          <EditField label="學歷" value={draft.education} onChange={(v) => updateDraft("education", v)} />
          <EditField
            label="經歷重點（可用換行、頓號或逗號分隔）"
            value={draft.experiences}
            onChange={(v) => updateDraft("experiences", v)}
            multiline
          />
          <div className="flex flex-wrap gap-2">
            <Button icon={Check} onClick={applyEdit}>套用修改</Button>
            <Button variant="secondary" icon={X} onClick={() => setEditing(false)}>取消</Button>
          </div>
        </div>
      ) : (
        <dl className="grid sm:grid-cols-2 gap-3 mt-4">
          <Meta label="Profile 名稱" value={activeProfile.label} />
          <Meta label="履歷" value={activeProfile.resumeLabel || "已解析履歷"} />
          <Meta label="目標職稱" value={roles.join("、")} />
          <Meta label="想強調技能" value={(preferences?.emphasize_skills?.length ? preferences.emphasize_skills : skills).join("、")} />
          <Meta label="語氣" value={preferences?.tone || ""} />
          <Meta label="更新時間" value={fmtDate(activeProfile.updatedAt)} />
        </dl>
      )}
      {onSaveActiveProfile && (
        <div className="mt-4 flex flex-col sm:flex-row gap-2">
          <input
            value={label}
            onChange={(e) => { setLabel(e.target.value); setSaved(false) }}
            aria-label="Profile 名稱"
            className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200"
            placeholder="Profile 名稱"
          />
          <Button icon={Save} onClick={saveActive}>
            {activeIsSaved ? "更新 Profile" : "儲存為 Profile"}
          </Button>
          {onUpdateActiveProfile && !editing && (
            <Button variant="secondary" icon={Pencil} onClick={startEdit}>編輯 Profile</Button>
          )}
          {onClearActiveProfile && (
            <Button variant="secondary" icon={X} onClick={onClearActiveProfile}>不使用 Profile</Button>
          )}
        </div>
      )}
      {saved && <p className="text-sm text-emerald-700 mt-2 inline-flex items-center gap-1">
        <CheckCircle2 className="w-4 h-4" />Profile 已儲存
      </p>}
    </div>
  )
}
