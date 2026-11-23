import { label, money, moneyShort, pct } from "../lib/format";

describe("format", () => {
  it("formats rand amounts the South African way", () => {
    expect(money(1330000).replace(/\s/g, " ")).toMatch(/^R\s?1.330.000$/);
    expect(moneyShort(4027000)).toBe("R4.03m");
    expect(moneyShort(955000)).toBe("R955k");
  });
  it("formats shares and labels", () => {
    expect(pct(0.1631)).toBe("16.3%");
    expect(pct(null)).toBe("-");
    expect(label("PENDING_APPROVAL")).toBe("Pending approval");
  });
});
