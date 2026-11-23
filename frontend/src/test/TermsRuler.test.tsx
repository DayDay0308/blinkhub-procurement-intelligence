import { render, screen } from "@testing-library/react";
import { TermsRuler } from "../components/TermsRuler";

describe("TermsRuler", () => {
  it("describes an overdue invoice for screen readers", () => {
    render(<TermsRuler days={45} state="BREACHED" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("45 days outstanding: past terms");
  });
  it("describes a paid invoice", () => {
    render(<TermsRuler days={12} state="PAID" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Paid in 12 days");
  });
  it("pins very old invoices to the end of the track", () => {
    render(<TermsRuler days={90} state="BREACHED" />);
    expect(screen.getByText("90d (60+)")).toBeInTheDocument();
  });
});
