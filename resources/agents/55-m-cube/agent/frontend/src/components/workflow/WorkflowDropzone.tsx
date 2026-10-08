import { Button } from "@/components/ui/button";

interface WorkflowDropzoneProps {
  title: string;
  hint: string;
  fileLabel: string;
  accept?: string;
  selectedFileName?: string;
  busy?: boolean;
  onSelectFile: (file: File | null) => void;
  onConfirm: () => void;
  confirmText: string;
  disabled?: boolean;
  extra?: import("react").ReactNode;
}

export function WorkflowDropzone({
  title,
  hint,
  fileLabel,
  accept,
  selectedFileName,
  busy,
  onSelectFile,
  onConfirm,
  confirmText,
  disabled,
  extra,
}: WorkflowDropzoneProps) {
  return (
    <section className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-100">
      <h2 className="text-base font-semibold text-gray-800">{title}</h2>
      <p className="mt-1 text-sm text-gray-500">{hint}</p>

      <label className="mt-4 block rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 p-8 text-center transition-colors hover:border-gray-400" htmlFor={`upload-${fileLabel}`}>
        <p className="text-sm text-gray-700">将文件拖拽到此处，或点击上传</p>
        <p className="mt-1 text-xs text-gray-500">支持 Word / PDF / TXT</p>
        <input
          accept={accept}
          className="hidden"
          id={`upload-${fileLabel}`}
          onChange={(event) => onSelectFile(event.target.files?.[0] ?? null)}
          type="file"
        />
      </label>

      <div className="mt-3 text-xs text-gray-500">{fileLabel}：{selectedFileName ?? "未选择文件"}</div>
      {extra ? <div className="mt-3">{extra}</div> : null}

      <div className="mt-4 flex justify-end">
        <Button disabled={busy || disabled} onClick={onConfirm}>
          {confirmText}
        </Button>
      </div>
    </section>
  );
}

