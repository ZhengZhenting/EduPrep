import { useEffect, useRef } from "react";
import mermaid from "mermaid";

let inited = false;
function initMermaid() {
  if (inited) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose",
    themeVariables: {
      background: "transparent",
      primaryColor: "#fef3c7",         // warm amber fill
      primaryTextColor: "#1c1917",     // dark warm text
      primaryBorderColor: "#d97706",   // amber border
      lineColor: "#b45309",            // dark amber lines
      fontFamily: "Space Grotesk, Inter, sans-serif",
    },
  });
  inited = true;
}

export function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    initMermaid();
    if (!ref.current || !chart) return;
    const id = `m${Math.random().toString(36).slice(2)}`;
    mermaid.render(id, chart).then(({ svg }) => {
      if (ref.current) ref.current.innerHTML = svg;
    }).catch(() => {
      if (ref.current) ref.current.innerHTML = `<pre class="text-xs text-muted-foreground p-4">${chart}</pre>`;
    });
  }, [chart]);
  return <div ref={ref} className="mermaid-wrap overflow-x-auto" />;
}
