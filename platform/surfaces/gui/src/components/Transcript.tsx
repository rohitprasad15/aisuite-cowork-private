import { useState } from "react";
import type { ApprovalDecision, Item } from "../types";

function shortArgs(args: any): string {
  if (!args || typeof args !== "object") return "";
  return Object.entries(args)
    .map(([k, v]) => {
      let s = typeof v === "string" ? v : JSON.stringify(v);
      if (s.length > 64) s = s.slice(0, 63) + "…";
      return `${k}=${s.replace(/\n/g, "⏎")}`;
    })
    .join("  ");
}

type ToolItem = Extract<Item, { kind: "tool" }>;

function ToolGroup({ tools }: { tools: ToolItem[] }) {
  const [open, setOpen] = useState(true);
  const running = tools.some((t) => t.status === "…");
  const label = running ? `Running ${tools.length} tool${tools.length > 1 ? "s" : ""}…` : `Ran ${tools.length} tool${tools.length > 1 ? "s" : ""}`;
  return (
    <div className="toolgroup">
      <div className="toolgroup-head" onClick={() => setOpen(!open)}>
        <span className="chev">{open ? "⌄" : "›"}</span> {label}
      </div>
      {open && (
        <div className="toolgroup-body">
          {tools.map((t, i) => (
            <div className="toolrow" key={i}>
              <span className={"status " + t.status}>
                {t.status === "ok" ? "✓" : t.status === "…" ? "…" : "•"}
              </span>
              <span className="name">{t.name}</span>
              <span className="rowargs">{shortArgs(t.args)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  items: Item[];
  onApprove: (decision: ApprovalDecision) => void;
}

export function Transcript({ items, onApprove }: Props) {
  // Group consecutive tool items into a collapsible block.
  const blocks: Array<{ tools: ToolItem[] } | { item: Item; i: number }> = [];
  let run: ToolItem[] = [];
  const flush = () => {
    if (run.length) {
      blocks.push({ tools: run });
      run = [];
    }
  };
  items.forEach((item, i) => {
    if (item.kind === "tool") run.push(item);
    else {
      flush();
      blocks.push({ item, i });
    }
  });
  flush();

  return (
    <div className="transcript">
      {blocks.map((block, bi) => {
        if ("tools" in block) return <ToolGroup tools={block.tools} key={bi} />;
        const { item } = block;
        switch (item.kind) {
          case "user":
            return (
              <div className="bubble-user" key={bi}>
                {item.attachments && item.attachments.length > 0 && (
                  <div className="bubble-attachments">
                    {item.attachments.map((a, i) =>
                      a.kind === "image" ? (
                        <img key={i} className="msg-img" src={a.data_url} alt={a.name} />
                      ) : (
                        <span key={i} className="msg-file">📄 {a.name}</span>
                      ),
                    )}
                  </div>
                )}
                {item.text}
              </div>
            );
          case "assistant":
            return (
              <div className="bubble-assistant" key={bi}>
                <div className="who">assistant</div>
                {item.text}
              </div>
            );
          case "approval":
            return (
              <div className="approval" key={bi}>
                <div className="title">Permission required</div>
                <div className="row">
                  <span className="k">tool</span>
                  <span className="v">{item.name}</span>
                </div>
                <div className="row">
                  <span className="k">args</span>
                  <span className="v">{shortArgs(item.args)}</span>
                </div>
                <div className="row">
                  <span className="k">reason</span>
                  <span className="v">{item.reason}</span>
                </div>
                {item.resolved ? (
                  <div className="resolved">→ {item.resolved.replace("_", " ")}</div>
                ) : (
                  <div className="approval-btns">
                    <button className="btn primary" onClick={() => onApprove("once")}>
                      Approve
                    </button>
                    <button className="btn danger" onClick={() => onApprove("deny")}>
                      Deny
                    </button>
                    <button className="btn" onClick={() => onApprove("always_tool")}>
                      Always this tool
                    </button>
                    <button className="btn" onClick={() => onApprove("always_command")}>
                      Always this command
                    </button>
                  </div>
                )}
              </div>
            );
          case "notice":
            return (
              <div className={"notice " + (item.tone === "warn" ? "warn" : "")} key={bi}>
                {item.text}
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
