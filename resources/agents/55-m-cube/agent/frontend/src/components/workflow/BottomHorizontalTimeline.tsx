import { cn } from "@/lib/utils";
import type { TimelineNodeVM } from "@/types/ui";

interface BottomHorizontalTimelineProps {
  nodes: TimelineNodeVM[];
  selectedNodeId: string;
  onSelectDoneNode: (id: string) => void;
}

function isCompleted(state: TimelineNodeVM["state"]) {
  return state === "done";
}

function isActive(state: TimelineNodeVM["state"]) {
  return state === "running" || state === "waiting_human";
}

function isReached(state: TimelineNodeVM["state"]) {
  return state !== "locked";
}

export function BottomHorizontalTimeline({
  nodes,
  selectedNodeId,
  onSelectDoneNode,
}: BottomHorizontalTimelineProps) {
  if (nodes.length === 0) return null;

  return (
    <div className="relative">
      <div className="no-scrollbar overflow-x-auto px-4 py-3">
        <ol className="relative flex min-w-max items-center gap-5">
          {nodes.map((node, index) => {
            const isSelected = node.id === selectedNodeId;
            const isDisabled = !node.clickable && node.state !== "ready";
            const stepNum = index + 1;
            const prev = index > 0 ? nodes[index - 1] : null;
            const connectorActive = !!prev && (isCompleted(prev.state) && isReached(node.state));
            return (
              <li className="relative flex items-center gap-3" key={node.id}>
                {index > 0 ? (
                  <span
                    className={cn(
                      "h-0.5 w-10 rounded-full",
                      connectorActive ? "bg-blue-500" : "bg-gray-200",
                    )}
                  />
                ) : null}
                <button
                  className={cn(
                    "group flex items-center gap-2 rounded-full px-2 py-1 text-left transition-colors",
                    isDisabled && "cursor-not-allowed opacity-70",
                  )}
                  disabled={isDisabled}
                  onClick={() => {
                    if (node.clickable || node.state === "ready") onSelectDoneNode(node.id);
                  }}
                  type="button"
                >
                  <span
                    className={cn(
                      "relative inline-flex h-8 w-8 items-center justify-center rounded-full border text-sm",
                      isCompleted(node.state) && "border-blue-500 bg-blue-500 text-white",
                      isActive(node.state) && "border-blue-500 bg-white text-blue-600 shadow-[0_0_0_4px_rgba(59,130,246,0.12)]",
                      (node.state === "locked" || node.state === "ready") &&
                        "border-gray-200 bg-gray-100 text-gray-400",
                      node.state === "error" && "border-amber-500 bg-amber-50 text-amber-600",
                      isSelected && "ring-2 ring-blue-200",
                    )}
                  >
                    {isCompleted(node.state) ? (
                      <span className="text-base leading-none">✓</span>
                    ) : isActive(node.state) ? (
                      <span className="inline-flex items-center">
                        <span className="absolute inline-flex h-8 w-8 animate-ping rounded-full bg-blue-100 opacity-30" />
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                      </span>
                    ) : (
                      <span>{stepNum}</span>
                    )}
                  </span>
                  <span
                    className={cn(
                      "text-xs",
                      isCompleted(node.state) && "font-medium text-gray-800",
                      isActive(node.state) && "font-medium text-blue-600",
                      (node.state === "locked" || node.state === "ready") && "text-gray-400",
                      node.state === "error" && "font-medium text-amber-600",
                    )}
                  >
                    {node.label}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
