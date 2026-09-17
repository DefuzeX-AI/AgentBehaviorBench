import { MyAssistant } from "@/components/MyAssistant";
import {
  useAssistantInstructions,
  useAssistantTool,
} from "@assistant-ui/react";

export default function Home() {
  // this is a frontend system prompt that will be made available to the langgraph agent
  useAssistantInstructions("Your name is assistant-ui.");

  // this is an frontend function that will be made available to the langgraph agent
  useAssistantTool({
    toolName: "refresh_page",
    description: "Refresh the page",
    parameters: {},
    execute: async () => {
      window.location.reload();
    },
  });

  return (
    <main className="h-dvh">
      <MyAssistant />
    </main>
  );
}
