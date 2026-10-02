import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ReadableContent from './ReadableContent.jsx';
import { inspectContent, readableMessages } from './contentFormat.js';

function Markdown({ text }) {
  return <div className="content-markdown"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]}
    components={{ img: () => null }}>{text}</ReactMarkdown></div>;
}

// Keep conversation text quiet; the evidence panel retains the original envelope.
export default function ReplayMessage({ value }) {
  const { raw, json, parsed, responseKey } = inspectContent(value);
  if (!json) return <Markdown text={raw} />;
  const messages = readableMessages(parsed);
  if (messages.length) return <>{messages.map((message, index) => <div className="replay-message-part" key={index}>
    {message.name && <small>{message.name}</small>}
    {typeof message.content === 'string' ? <Markdown text={message.content} />
      : Array.isArray(message.content) ? message.content.map((block, i) =>
        typeof block === 'string' ? <Markdown key={i} text={block} />
          : ['text', 'input_text', 'output_text'].includes(block?.type) && typeof block.text === 'string'
            ? <Markdown key={i} text={block.text} /> : <ReadableContent key={i} value={block} />)
        : <ReadableContent value={message.content} />}
    {!!message.tools?.length && <details className="replay-message-tools"><summary>Tool calls · {message.tools.length}</summary>
      <ReadableContent value={message.tools} /></details>}
  </div>)}</>;
  if (responseKey) return <Markdown text={parsed[responseKey]} />;
  return <ReadableContent value={value} />;
}
