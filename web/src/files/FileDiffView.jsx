import { FileDiff } from '@pierre/diffs/react';

export default function FileDiffView({ file, layout }) {
  return <div className="formatted-file-diff" aria-label={`${layout === 'split' ? 'Side-by-side' : 'Unified'} file diff`}>
    <FileDiff fileDiff={file} options={{ diffStyle: layout, theme: 'github-light', themeType: 'light', overflow: 'wrap',
      diffIndicators: 'classic', disableFileHeader: true, lineDiffType: 'word' }} />
  </div>;
}
