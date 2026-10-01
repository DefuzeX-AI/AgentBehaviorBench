import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { File } from '@pierre/diffs/react';

export default function FileContentPreview({ path, content }) {
  if (/\.(md|markdown|mdown)$/i.test(path)) return <article className="file-content-preview file-markdown-preview" aria-label="Markdown file preview">
    <ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{ img: () => null,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{content}</ReactMarkdown>
  </article>;
  return <div className="file-content-preview" aria-label="File content preview"><File file={{ name: path, contents: content }}
    options={{ theme: 'github-light', themeType: 'light', overflow: 'wrap', disableFileHeader: true }} /></div>;
}
