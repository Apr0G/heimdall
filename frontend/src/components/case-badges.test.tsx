/**
 * The two band badges have OPPOSITE polarity by design: high appeal
 * probability is good (green), high denial risk is bad (red). This pins the
 * mapping so nobody "unifies" them into one badge and silently shows a
 * high-risk claim in reassuring green.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProbabilityBadge, RiskBadge } from "./case-badges";

function style(text: string | RegExp): string {
  return screen.getByText(text).getAttribute("style") ?? "";
}

describe("band badge polarity", () => {
  it("high appeal probability renders in the ok token", () => {
    render(<ProbabilityBadge band="high" />);
    expect(style("high")).toContain("--ok");
  });

  it("high denial risk renders in the danger token", () => {
    render(<RiskBadge band="high" />);
    expect(style(/high risk/)).toContain("--danger");
  });

  it("low denial risk renders in the ok token", () => {
    render(<RiskBadge band="low" />);
    expect(style(/low risk/)).toContain("--ok");
  });

  it("no band renders the no-flags text, not a colored pill", () => {
    render(<RiskBadge band={null} />);
    expect(screen.getByText("No flags")).toBeInTheDocument();
  });
});
