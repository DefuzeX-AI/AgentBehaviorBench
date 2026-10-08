import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "@/App";
import { HitlActionPanel } from "@/components/hitl/HitlActionPanel";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

class MockEventSource {
  close() {
    return undefined;
  }
  addEventListener() {
    return undefined;
  }
  onopen: ((this: EventSource, ev: Event) => unknown) | null = null;
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null;
}

describe("dual-pane workspace", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("renders left and right workspace areas", () => {
    render(<App />);
    fireEvent.click(screen.getAllByRole("button")[1]);

    expect(screen.getByText("HITL 人工交互")).toBeInTheDocument();
  });

  test("hitl submit button enabled only with input", async () => {
    const user = userEvent.setup();
    const onSubmitClaims = vi.fn();
    const onSubmitAutoReviseClaims = vi.fn();
    const onSubmitSpecReview = vi.fn();
    render(
      <HitlActionPanel
        busy={false}
        onSubmitClaims={onSubmitClaims}
        onSubmitAutoReviseClaims={onSubmitAutoReviseClaims}
        onSubmitSpecReview={onSubmitSpecReview}
        stage="claims_review"
        visible
      />,
    );

    const submitButton = screen.getByRole("button", { name: "提交已确认权利要求" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("请粘贴或编辑权利要求 JSON..."), {
      target: { value: "{\"ok\": true}" },
    });
    expect(submitButton).toBeEnabled();
    await user.click(submitButton);

    expect(onSubmitClaims).toHaveBeenCalledTimes(1);
  });

  test("spec review hitl shows targeted revision confirm button", async () => {
    const user = userEvent.setup();
    const onSubmitClaims = vi.fn();
    const onSubmitAutoReviseClaims = vi.fn();
    const onSubmitSpecReview = vi.fn();
    render(
      <HitlActionPanel
        busy={false}
        onSubmitClaims={onSubmitClaims}
        onSubmitAutoReviseClaims={onSubmitAutoReviseClaims}
        onSubmitSpecReview={onSubmitSpecReview}
        stage="spec_review"
        visible
      />,
    );

    const confirmButton = screen.getByRole("button", { name: "确认并执行说明书小改" });
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);
    expect(onSubmitSpecReview).toHaveBeenCalledTimes(1);
  });
});
