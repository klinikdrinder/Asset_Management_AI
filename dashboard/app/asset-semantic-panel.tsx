import type { AssetSemanticDetail } from "./queries";

// Server-rendered 18-layer evidence breakdown for an asset. Each layer is a collapsible group
// showing its assertions with state + confidence, the canonical concept code when one exists, and
// the AI-derived description text. Pre-normalisation most layers carry prose with placeholder codes
// (see the recon) — this still gives reviewers the full grounded picture per layer.
const stateClass = (state: string) => (state === "OBSERVED" ? "chipObserved" : state === "FALSE" ? "chipFalse" : "chipUnknown");

export function AssetSemanticPanel({ detail }: { detail: AssetSemanticDetail }) {
  if (!detail.layers.length) return null;
  return (
    <section className="layerPanel" aria-label="18-layer semantic evidence">
      <h3>Semantic evidence · {detail.layers.length} layers</h3>
      {detail.layers.map((layer) => (
        <details className="layerGroup" key={layer.layerId}>
          <summary>{layer.label}<span className="layerCount">{layer.items.length}</span></summary>
          <ul>
            {layer.items.slice(0, 50).map((item, i) => (
              <li className="layerItem" key={i}>
                <span className={`evidenceChip ${stateClass(item.state)}`}>
                  {item.state}{item.confidence != null && <em> {Math.round(item.confidence * 100)}%</em>}
                </span>
                {item.code && <span className="conceptCode">{item.code}</span>}
                {item.text && <span className="layerText">{item.text}</span>}
              </li>
            ))}
            {layer.items.length > 50 && <li className="layerMore">+{layer.items.length - 50} more</li>}
          </ul>
        </details>
      ))}
    </section>
  );
}
