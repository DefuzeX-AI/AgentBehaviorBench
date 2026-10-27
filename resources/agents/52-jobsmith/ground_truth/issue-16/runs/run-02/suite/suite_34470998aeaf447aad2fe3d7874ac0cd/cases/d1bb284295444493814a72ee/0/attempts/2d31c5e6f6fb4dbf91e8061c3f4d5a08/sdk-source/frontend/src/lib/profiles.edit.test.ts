import type { UserProfile } from "../types"
import { editableProfileFromUserProfile, userProfileFromEditableProfile } from "./profiles.ts"

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message)
}

const parsedProfile: UserProfile = {
  name: "王予",
  summary: "AI 工程師",
  skills: ["Codex"],
  preferred_roles: ["前端工程師"],
  raw_text: "PDF text layer only exposed the partial name.",
}

const editable = editableProfileFromUserProfile(parsedProfile)
assert(editable.name === "王予", "editable profile should expose parsed name")

const corrected = userProfileFromEditableProfile({
  ...editable,
  name: "王予辰",
  skills: "Codex\nClaude Code、FastAPI",
  preferred_roles: "AI 工程師, 前端工程師",
}, parsedProfile)

assert(corrected.name === "王予辰", "manual correction should replace parsed name")
assert(Array.isArray(corrected.skills), "skills should be normalized to an array")
assert((corrected.skills as string[]).includes("Claude Code"), "skills should split on newline and punctuation")
assert((corrected.preferred_roles as string[])[0] === "AI 工程師", "preferred roles should preserve order")
assert(corrected.raw_text === parsedProfile.raw_text, "unknown/base profile fields should be preserved")
