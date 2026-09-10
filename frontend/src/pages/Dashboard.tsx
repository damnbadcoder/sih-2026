import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Markdown from "../components/Markdown";
import {
  generateDeliverable,
  generatePlan,
  regenerateDeliverable,
} from "../lib/mock";
import {
  AUDIENCE_CATEGORIES,
  DEFAULT_PARAMS,
  DETAIL_LEVELS,
  LANGUAGES,
  OBJECTIVES,
  OUTPUT_TYPES,
  TONES,
  outputTypeLabel,
} from "../lib/types";
import type {
  Citation,
  Deliverable,
  Generation,
  GenerationParams,
  OutputTypeId,
  User,
} from "../lib/types";

const HISTORY_KEY = "tx.history";

function loadHistory(): Generation[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]") as Generation[];
  } catch {
    return [];
  }
}

function copyParams(params: GenerationParams): GenerationParams {
  return { ...params };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const user = useMemo<User | null>(() => {
    try {
      return JSON.parse(localStorage.getItem("tx.user") ?? "null") as User | null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!user) navigate("/login", { replace: true });
  }, [user, navigate]);

  const [sourceTab, setSourceTab] = useState<"text" | "files" | "links">("text");
  const [sourceText, setSourceText] = useState("");
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [links, setLinks] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const [selected, setSelected] = useState<Set<OutputTypeId>>(new Set());
  const [paramsByType, setParamsByType] = useState<Partial<Record<OutputTypeId, GenerationParams>>>({});
  const [openParams, setOpenParams] = useState<OutputTypeId | null>(null);

  const [planning, setPlanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [preview, setPreview] = useState("");
  const [previewCitations, setPreviewCitations] = useState<Citation[]>([]);
  const [gen, setGen] = useState<Generation | null>(null);
  const [activeId, setActiveId] = useState<OutputTypeId | null>(null);
  const [history, setHistory] = useState<Generation[]>(loadHistory);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [refinement, setRefinement] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState(false);

  const active: Deliverable | undefined = gen?.deliverables.find(
    (d) => d.outputType === activeId
  );
  const isPreviewStage = Boolean(preview) && !gen;

  function paramsFor(id: OutputTypeId): GenerationParams {
    return paramsByType[id] ?? copyParams(DEFAULT_PARAMS);
  }

  function updateParams(id: OutputTypeId, patch: Partial<GenerationParams>) {
    setParamsByType((prev) => ({
      ...prev,
      [id]: { ...paramsFor(id), ...patch },
    }));
  }

  function toggleOutput(id: OutputTypeId) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setOpenParams((current) => (current === id ? null : current));
      } else {
        next.add(id);
        setOpenParams(id);
      }
      return next;
    });
  }

  function sourceSummary(g: Generation): string {
    const parts: string[] = [];
    if (g.sourceText.trim()) parts.push(`${g.sourceText.trim().length.toLocaleString()} chars of text`);
    if (g.fileNames.length) parts.push(`${g.fileNames.length} file(s)`);
    if (g.links.length) parts.push(`${g.links.length} link(s)`);
    return parts.join(" · ") || "empty source";
  }

  async function createPreview() {
    setGenError("");
    const hasText = sourceText.trim().length > 0;
    const hasFiles = fileNames.length > 0;
    const sourceLinks = links.split("\n").map((link) => link.trim()).filter(Boolean);
    if (!hasText && !hasFiles && sourceLinks.length === 0) {
      setGenError("Provide source content — paste text, upload files or add links.");
      return;
    }
    if (selected.size === 0) {
      setGenError("Select at least one output type.");
      return;
    }

    setPlanning(true);
    try {
      const result = await generatePlan(
        sourceText,
        fileNames,
        sourceLinks,
        Array.from(selected).map((id) => ({ id, params: paramsFor(id) }))
      );
      setPreview(result.plan);
      setPreviewCitations(result.citations);
      setGen(null);
    } finally {
      setPlanning(false);
    }
  }

  async function finalizeGeneration() {
    setGenError("");
    setGenerating(true);
    const sourceLinks = links.split("\n").map((link) => link.trim()).filter(Boolean);
    const g: Generation = {
      id: crypto.randomUUID(),
      createdAt: Date.now(),
      sourceText,
      fileNames,
      links: sourceLinks,
      paramsByType: Object.fromEntries(
        Array.from(selected).map((id) => [id, paramsFor(id)])
      ) as Record<OutputTypeId, GenerationParams>,
      plan: preview,
      citations: previewCitations,
      deliverables: [],
    };

    try {
      const first = selected.values().next().value as OutputTypeId;
      for (const id of selected) {
        const content = await generateDeliverable(id, sourceText, paramsFor(id));
        g.deliverables.push({ outputType: id, content, retries: 0 });
        setGen({ ...g, deliverables: [...g.deliverables] });
        if (id === first) setActiveId(id);
      }
      const done = { ...g, deliverables: [...g.deliverables] };
      const nextHistory = [done, ...history].slice(0, 20);
      setHistory(nextHistory);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(nextHistory));
      setPreview("");
      setPreviewCitations([]);
      setOpenParams(null);
    } catch {
      setGenError("The model could not create the deliverables. Please try again.");
    } finally {
      setGenerating(false);
    }
  }

  async function retry() {
    if (!gen || !active || !activeId) return;
    setRetrying(true);
    try {
      const content = await regenerateDeliverable(
        activeId,
        gen.sourceText,
        paramsFor(activeId),
        refinement || "Improve overall quality and clarity"
      );
      setGen({
        ...gen,
        deliverables: gen.deliverables.map((d) =>
          d.outputType === activeId ? { ...d, content, retries: d.retries + 1 } : d
        ),
      });
    } finally {
      setRetrying(false);
    }
  }

  function openHistory(item: Generation) {
    setGen(item);
    setPreview(item.plan);
    setPreviewCitations(item.citations);
    setActiveId(item.deliverables[0]?.outputType ?? null);
    setSelected(new Set(item.deliverables.map((d) => d.outputType)));
    setParamsByType(item.paramsByType);
    setSourceText(item.sourceText);
    setFileNames(item.fileNames);
    setLinks(item.links.join("\n"));
    setEditing(false);
    setOpenParams(null);
  }

  function acceptDraft() {
    if (!gen || !activeId) return;
    setGen({
      ...gen,
      deliverables: gen.deliverables.map((d) =>
        d.outputType === activeId ? { ...d, content: draft } : d
      ),
    });
    setEditing(false);
  }

  async function copy() {
    if (!active) return;
    await navigator.clipboard.writeText(active.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function download() {
    if (!active) return;
    const blob = new Blob([active.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${active.outputType}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function logout() {
    localStorage.removeItem("tx.user");
    navigate("/login", { replace: true });
  }

  if (!user) return null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="logo-mark sm">⌁</span> Transmute</div>
        <div className="topbar-right">
          <span className="user-chip">{user.name} · <em>{user.userType}</em></span>
          <button className="ghost" onClick={logout}>Sign out</button>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-user">
            <div className="avatar">{user.name.slice(0, 1).toUpperCase()}</div>
            <div><strong>{user.name}</strong><span>{user.email}</span><span>{user.organisation || user.userType}</span></div>
          </div>
          <h2 className="col-title">History</h2>
          {history.length === 0 ? <p className="muted sidebar-empty">No generations yet.</p> : (
            <ul className="card history">
              {history.map((item) => (
                <li key={item.id}>
                  <button onClick={() => openHistory(item)}>
                    <strong>{item.deliverables.map((d) => outputTypeLabel(d.outputType)).join(", ")}</strong>
                    <span className="muted">{new Date(item.createdAt).toLocaleDateString()} · {sourceSummary(item)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="col-input">
          <h2 className="col-title">1 · Source content</h2>
          <div className="card">
            <div className="segmented full">
              {(["text", "files", "links"] as const).map((tab) => (
                <button key={tab} className={sourceTab === tab ? "on" : ""} onClick={() => setSourceTab(tab)}>
                  {tab === "text" ? "Text / Prompt" : tab[0].toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
            {sourceTab === "text" && <textarea className="source-text" placeholder="Paste an article, report, advisory, incident note, or a free-form prompt…" value={sourceText} onChange={(e) => setSourceText(e.target.value)} rows={10} />}
            {sourceTab === "files" && (
              <div className="dropzone">
                <button className="ghost" onClick={() => fileInput.current?.click()}>Attach files</button>
                <input ref={fileInput} type="file" multiple hidden accept=".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.mp4,.mov,.webm" onChange={(e) => setFileNames((prev) => [...new Set([...prev, ...Array.from(e.target.files ?? []).map((file) => file.name)])])} />
                <p className="muted">PDF · DOCX · images · video · plain text</p>
                {fileNames.length > 0 && <ul className="file-list">{fileNames.map((name) => <li key={name}>{name}<button className="x" onClick={() => setFileNames((prev) => prev.filter((item) => item !== name))}>×</button></li>)}</ul>}
              </div>
            )}
            {sourceTab === "links" && <textarea className="source-text" placeholder={"https://example.org/threat-report\nhttps://news.example.com/breach"} value={links} onChange={(e) => setLinks(e.target.value)} rows={5} />}
          </div>

          <h2 className="col-title">2 · Output types <span className="muted">({selected.size} selected)</span></h2>
          <div className="card output-grid">
            {OUTPUT_TYPES.map((type) => {
              const chosen = selected.has(type.id);
              const configured = openParams === type.id;
              return (
                <button key={type.id} className={`output-tile ${chosen ? "on" : ""} ${configured ? "configuring" : ""}`} onClick={() => toggleOutput(type.id)}>
                  <strong>{type.label}</strong><span>{type.hint}</span>
                  {chosen && <small>{configured ? "Editing parameters" : "Selected"}</small>}
                </button>
              );
            })}
          </div>
          {!preview && (
            <button className="primary generate" onClick={createPreview} disabled={planning}>
              {planning ? "Preparing preview…" : `Create editable preview${selected.size ? ` · ${selected.size} output${selected.size === 1 ? "" : "s"}` : ""}`}
            </button>
          )}
          {genError && <p className="form-error">{genError}</p>}
        </main>

        <section className="col-output">
          {isPreviewStage && (
            <>
              <h2 className="col-title">Preview before delivery</h2>
              <div className="card preview-card">
                <div className="preview-toolbar">
                  <span className="muted">Editable model instructions</span>
                  <button className="ghost" onClick={() => setPreview("")}>Back to setup</button>
                </div>
                <textarea className="md-editor preview-editor" value={preview} onChange={(e) => setPreview(e.target.value)} />
                <div className="citation-box">
                  <strong>Suggested citations</strong>
                  <p className="muted">Reference these sources when a claim is included in the final output.</p>
                  <div className="citation-list">{previewCitations.map((citation) => <span key={citation.id} className="citation-chip">{citation.kind === "file" ? "▣" : citation.kind === "link" ? "↗" : "¶"} {citation.label}</span>)}</div>
                </div>
                <button className="primary" onClick={finalizeGeneration} disabled={generating}>{generating ? "Sending to model…" : "Done — generate deliverables"}</button>
              </div>
            </>
          )}

          {!gen && !isPreviewStage && !planning && <div className="card empty"><p>No deliverables yet.</p><p className="muted">Create a preview to review what the model will do before delivery.</p></div>}
          {planning && <div className="card empty"><p className="pulse">Analysing source and preparing an editable preview…</p></div>}

          {gen && (
            <>
              <h2 className="col-title">Deliverables</h2>
              <div className="result-meta"><span>{sourceSummary(gen)}</span><span className="muted">{new Date(gen.createdAt).toLocaleString()}</span></div>
              <div className="tabs" role="tablist">{gen.deliverables.map((item) => <button key={item.outputType} role="tab" aria-selected={item.outputType === activeId} className={item.outputType === activeId ? "on" : ""} onClick={() => { setActiveId(item.outputType); setEditing(false); }}>{outputTypeLabel(item.outputType)}{item.retries > 0 && <sup>{item.retries}</sup>}</button>)}</div>
              {active && <div className="card deliverable">
                <div className="deliverable-toolbar">{editing ? <><button className="ghost" onClick={() => setEditing(false)}>Discard</button><button className="primary" onClick={acceptDraft}>Save changes</button></> : <><button className="ghost" onClick={() => { setDraft(active.content); setEditing(true); }}>Edit markdown</button><button className="ghost" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button><button className="ghost" onClick={download}>Download .md</button></>}</div>
                {editing ? <textarea className="md-editor" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} /> : <Markdown content={active.content} />}
              </div>}
              {active && !editing && <div className="card retry"><strong>Not satisfied?</strong><textarea placeholder="Describe what to change — e.g. “shorter, drop the jargon, add a call to action”" value={refinement} onChange={(e) => setRefinement(e.target.value)} rows={2} /><button className="primary" onClick={retry} disabled={retrying}>{retrying ? "Regenerating…" : "Retry with this instruction"}</button></div>}
            </>
          )}
        </section>

        {openParams && !gen && !preview && (
          <section className="params-panel">
            <div className="params-heading"><h2 className="col-title">Parameters · {outputTypeLabel(openParams)}</h2><button className="ghost" onClick={() => setOpenParams(null)}>Close</button></div>
            <div className="card param-grid">
              <label>Audience category<select value={paramsFor(openParams).audienceCategory} onChange={(e) => updateParams(openParams, { audienceCategory: e.target.value as GenerationParams["audienceCategory"] })}>{AUDIENCE_CATEGORIES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              <label>Target audience <span className="opt">(optional)</span><input placeholder="e.g. bank CISOs, district collectors" value={paramsFor(openParams).targetAudience} onChange={(e) => updateParams(openParams, { targetAudience: e.target.value })} /></label>
              <label>Tone<select value={paramsFor(openParams).tone} onChange={(e) => updateParams(openParams, { tone: e.target.value as GenerationParams["tone"] })}>{TONES.map((tone) => <option key={tone}>{tone}</option>)}</select></label>
              <label>Level of detail<select value={paramsFor(openParams).detail} onChange={(e) => updateParams(openParams, { detail: e.target.value as GenerationParams["detail"] })}>{DETAIL_LEVELS.map((detail) => <option key={detail}>{detail}</option>)}</select></label>
              <label>Objective<select value={paramsFor(openParams).objective} onChange={(e) => updateParams(openParams, { objective: e.target.value as GenerationParams["objective"] })}>{OBJECTIVES.map((objective) => <option key={objective}>{objective}</option>)}</select></label>
              <label>Language<select value={paramsFor(openParams).language} onChange={(e) => updateParams(openParams, { language: e.target.value })}>{LANGUAGES.map((language) => <option key={language}>{language}</option>)}</select></label>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
