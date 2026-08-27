import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  SCENE,
  SceneBill,
  SceneCapture,
  SceneCollect,
  SceneDeliver,
  SceneManage,
  SceneUnderstand,
} from "./scenes";
import { MARK_PATH } from "./logo";

/**
 * The illustrated lifecycle (LACTEVA-MARKETING-005). The rules worth
 * pinning are the ones that would rot silently: every scene is
 * decorative, the indigo accent means "computed signal" and appears in
 * exactly one scene, and the van carries the generated mark — not a
 * hand-drawn cousin, which is how this brand once ended up with three.
 */
const SCENES = [
  ["Capture", SceneCapture],
  ["Manage", SceneManage],
  ["Deliver", SceneDeliver],
  ["Bill", SceneBill],
  ["Collect", SceneCollect],
  ["Understand", SceneUnderstand],
] as const;

describe("the lifecycle scenes", () => {
  it.each(SCENES)("%s renders as a decorative SVG", (_name, Scene) => {
    const { container } = render(<Scene />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("spends the indigo intelligence accent on exactly one scene — the computed signal", () => {
    const carriers = SCENES.filter(([, Scene]) => {
      const { container } = render(<Scene />);
      return container.innerHTML.includes(SCENE.indigo);
    }).map(([name]) => name);
    expect(carriers).toEqual(["Understand"]);
  });

  it("the delivery van carries the generated mark, not a drawn cousin", () => {
    const { container } = render(<SceneDeliver />);
    expect(container.innerHTML).toContain(MARK_PATH);
  });
});
