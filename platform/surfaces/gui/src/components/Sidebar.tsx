import type { RecentWorkspace } from "../api";
import type { SessionInfo } from "../types";
import { Icon } from "./Icon";

interface Props {
  agent: string;
  workspace: string;
  model: string;
  mode: string;
  sessions: SessionInfo[];
  projects: RecentWorkspace[];
  activeSession: string;
  onSwitchAgent: (agent: string) => void;
  onNewSession: () => void;
  onSelectSession: (id: string, workspace: string, agent: string) => void;
  onNewProject: () => void;
  onManage: () => void;
  onOpenSuperagent: () => void;
  onOpenScheduled: () => void;
  superagentActive: boolean;
  scheduledActive: boolean;
  helperName?: string;
}

const baseName = (p: string) => p.split("/").filter(Boolean).pop() || p;
const needsWorkspace = (a: string) => a === "code" || a === "cowork";

export function Sidebar(props: Props) {
  const mine = props.sessions.filter((s) => s.agent === props.agent);
  const onSurface = props.superagentActive || props.scheduledActive;
  const workspaceSurface = !onSurface && needsWorkspace(props.agent);

  const sessionRow = (s: SessionInfo) => (
    <div
      key={s.session_id}
      className={"session" + (s.session_id === props.activeSession ? " active" : "")}
      onClick={() => props.onSelectSession(s.session_id, s.workspace, s.agent)}
      title={s.title || s.session_id}
    >
      {s.title || s.session_id}
    </div>
  );

  // Code groups by project; Chat is a flat recents list.
  const byProject = new Map<string, SessionInfo[]>();
  for (const s of mine) {
    if (!byProject.has(s.workspace)) byProject.set(s.workspace, []);
    byProject.get(s.workspace)!.push(s);
  }
  // Projects are tracked PER SURFACE: a folder appears under Code only if it has Code sessions,
  // under Cowork only if it has Cowork sessions (+ the currently-open folder). No cross-bleed.
  const projectOrder: string[] = [];
  const seen = new Set<string>();
  if (props.workspace) {
    projectOrder.push(props.workspace);
    seen.add(props.workspace);
  }
  for (const s of mine) {
    if (s.workspace && !seen.has(s.workspace)) {
      seen.add(s.workspace);
      projectOrder.push(s.workspace);
    }
  }

  return (
    <div className="sidebar">
      <div className="brand">
        <Icon name="sparkle" size={17} className="mark" />
        <span className="name">coworker</span>
      </div>

      <div
        className={"helper-row" + (props.superagentActive ? " active" : "")}
        onClick={props.onOpenSuperagent}
        title="Your always-on personal helper"
      >
        <Icon name="sparkle" size={18} className="mark" />
        <span className="helper-text">
          <span className="helper-name">{props.helperName || "MyHelper"}</span>
          <span className="helper-desc">Personal assistant</span>
        </span>
      </div>

      <div className="tabs">
        <div
          className={"tab" + (!onSurface && props.agent === "chat" ? " active" : "")}
          onClick={() => props.onSwitchAgent("chat")}
        >
          Chat
        </div>
        <div
          className={"tab tab-code" + (!onSurface && props.agent === "code" ? " active" : "")}
          onClick={() => props.onSwitchAgent("code")}
        >
          <Icon name="code" size={15} /> Code
        </div>
        <div
          className={"tab" + (!onSurface && props.agent === "cowork" ? " active" : "")}
          onClick={() => props.onSwitchAgent("cowork")}
          title="Spin up an agent to solve a problem and produce a deliverable"
        >
          Cowork
        </div>
      </div>

      <div className="newbtn" onClick={props.onNewSession}>
        <Icon name="plus" size={16} /> New {props.agent === "chat" ? "chat" : "session"}
      </div>

      {workspaceSurface ? (
        <>
          <div className="section-label">Projects</div>
          <div className="sessions">
            <div className="proj-new" onClick={props.onNewProject}>
              <Icon name="folderPlus" size={17} className="ico" /> New project
            </div>
            {projectOrder.map((proj) => (
              <div className="proj-group" key={proj}>
                <div
                  className={"proj-head" + (proj === props.workspace ? " current" : "")}
                  title={proj}
                >
                  <Icon name="folder" size={16} className="ico" />
                  <span className="pname">{baseName(proj)}</span>
                </div>
                {(byProject.get(proj) || []).map(sessionRow)}
              </div>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="section-label">Recents</div>
          <div className="sessions">
            {mine.length === 0 && (
              <div className="session" style={{ color: "var(--faint)" }}>
                No chats yet
              </div>
            )}
            {mine.map(sessionRow)}
          </div>
        </>
      )}

      <div className="sidebar-foot">
        <div
          className={"manage-link" + (props.scheduledActive ? " active" : "")}
          onClick={props.onOpenScheduled}
        >
          <Icon name="clock" size={15} className="ico" /> Scheduled
        </div>
        <div className="manage-link" onClick={props.onManage}>
          <Icon name="sliders" size={15} className="ico" /> Manage
        </div>
        {workspaceSurface && (
          <div className="ws" title={props.workspace}>
            {props.workspace || "—"}
          </div>
        )}
        <div>
          {props.model} · {props.mode}
        </div>
      </div>
    </div>
  );
}
