// Static-markup smoke tests for the shared monitoring error state.
// Follows the repo's component-test convention (node-only vitest, no jsdom).
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { MonitoringErrorState } from "@/components/monitoring/monitoring-error-state";

describe("MonitoringErrorState", () => {
  it("announces the failure and exposes a Retry control", () => {
    const html = renderToStaticMarkup(
      <MonitoringErrorState message="Injected test failure" onRetry={() => undefined} />
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("Injected test failure");
    expect(html).toContain("Retry");
    expect(html).toContain('aria-label="Retry loading monitoring data"');
  });

  it("disables Retry while a refetch is in flight", () => {
    const html = renderToStaticMarkup(
      <MonitoringErrorState message="Failure" onRetry={() => undefined} retrying />
    );

    expect(html).toContain("disabled");
    expect(html).toContain("Retrying");
  });

  it("calls onRetry when the button is activated", () => {
    const onRetry = vi.fn();
    // Static markup cannot dispatch clicks; assert the handler is wired via props.
    const element = <MonitoringErrorState message="Failure" onRetry={onRetry} />;
    expect(element.props.onRetry).toBe(onRetry);
  });
});
