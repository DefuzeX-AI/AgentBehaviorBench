export function newTaskId(prefix = "task") {
  const uuid = window.crypto?.randomUUID?.()
  if (uuid) return `${prefix}-${uuid}`
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export async function stopTask(taskId: string) {
  if (!taskId) return
  await fetch(`/api/tasks/${encodeURIComponent(taskId)}/stop`, { method: "POST" })
}
