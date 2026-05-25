"use client";

import { useEffect } from "react";

export default function LegacyRuntime() {
  useEffect(() => {
    if (window.__MMW_LEGACY_BOOTSTRAPPED__) {
      return;
    }
    window.__MMW_LEGACY_BOOTSTRAPPED__ = true;
    import("../src/legacy-app.js").catch((error) => {
      window.__MMW_LEGACY_BOOTSTRAPPED__ = false;
      console.error("MathModelingWorkbench runtime failed to load", error);
    });
  }, []);

  return null;
}
