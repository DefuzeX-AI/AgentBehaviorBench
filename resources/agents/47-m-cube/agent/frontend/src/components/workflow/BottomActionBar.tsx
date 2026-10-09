import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface BottomActionBarProps {
  disabled?: boolean;
  onCopy: () => void;
  onExportWord: () => void;
  className?: string;
}

export function BottomActionBar({ disabled, onCopy, onExportWord, className }: BottomActionBarProps) {
  return (
    <div className={cn("rounded-xl border border-gray-200 bg-white/95 p-3 shadow-sm backdrop-blur", className)}>
      <div className="flex items-center justify-end gap-2">
        <Button disabled={disabled} onClick={onCopy} variant="outline">
          一键复制全文
        </Button>
        <Button disabled={disabled} onClick={onExportWord}>
          导出为 Word
        </Button>
      </div>
    </div>
  );
}

