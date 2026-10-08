import { cn } from "@/lib/utils";
import { type GlobalTab } from "@/components/workflow/workflowConfig";

interface AppSidebarProps {
  activeTab: GlobalTab;
  onSelect: (tab: GlobalTab) => void;
}

const NAV_ITEMS: Array<{ id: GlobalTab; label: string }> = [
  { id: "home", label: "首页" },
  { id: "draft", label: "说明书撰写" },
  { id: "oa", label: "OA 答复" },
  { id: "compare", label: "专利对比" },
  { id: "polish", label: "专利润色" },
  { id: "settings", label: "设置" },
];

export function AppSidebar({ activeTab, onSelect }: AppSidebarProps) {
  return (
    <aside className="h-screen w-64 shrink-0 border-r border-gray-200 bg-gray-50 px-3 py-4">
      <div className="mb-6 px-2 text-sm font-semibold text-gray-700">M-Cube</div>
      <nav className="space-y-1">
        {NAV_ITEMS.map((item) => (
          <button
            className={cn(
              "w-full rounded-lg px-3 py-2 text-left text-sm transition-colors",
              activeTab === item.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
            )}
            key={item.id}
            onClick={() => onSelect(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

