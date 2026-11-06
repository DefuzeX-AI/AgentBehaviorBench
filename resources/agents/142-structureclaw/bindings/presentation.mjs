// Project native clarification events without inventing responses or dropping state.
export function presentState(state, chunks = []) {
  const interrupts = (state.__interrupt__ ?? []).map(item => item.value ?? item);
  for (const chunk of chunks) {
    if (chunk.type === 'interaction_update' && chunk.content?.resumeRequired) {
      for (const question of chunk.content.questions ?? []) {
        interrupts.push({question: question.question, options: chunk.content.options ?? []});
      }
    }
  }
  const lastMessage = state.messages?.at(-1);
  const response = interrupts.length
    ? interrupts.map(value => [value.question, ...(value.options ?? [])].filter(Boolean).map(
      item => typeof item === 'string' ? item : JSON.stringify(item)).join('\n')).join('\n\n')
    : typeof lastMessage?.content === 'string'
      ? lastMessage.content : JSON.stringify(lastMessage?.content ?? '');
  return {response, state, interrupts, chunks};
}
