import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Shell } from "../components/shell";
import { setToken } from "../lib/auth";

let mockPathname = "/suppliers";
const mockReplace = jest.fn();

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: mockReplace }),
}));

function jwtWithExpiry(exp: number): string {
  const payload = btoa(JSON.stringify({ exp }));
  return `header.${payload}.signature`;
}

describe("Shell authentication guard", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mockPathname = "/suppliers";
    mockReplace.mockClear();
    localStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  it("allows a protected route after login even if it redirected before", async () => {
    await act(async () => {
      root.render(<Shell><p>Contenido protegido</p></Shell>);
    });
    expect(mockReplace).toHaveBeenCalledWith("/login");

    mockPathname = "/login";
    await act(async () => {
      root.render(<Shell><p>Contenido protegido</p></Shell>);
    });

    setToken(jwtWithExpiry(Date.now() / 1000 + 60));
    mockPathname = "/suppliers";
    await act(async () => {
      root.render(<Shell><p>Contenido protegido</p></Shell>);
    });

    expect(mockReplace).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Contenido protegido");
  });
});
