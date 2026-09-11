export type UserType =
  | "Organisation"
  | "Government Agency"
  | "Influencer"
  | "Researcher"
  | "Journalist"
  | "Individual";

export interface User {
  name: string;
  email: string;
  userType: UserType;
  organisation?: string;
}

export type OutputTypeId =
  | "advisory"
  | "exec_summary"
  | "incident_report"
  | "social_thread"
  | "linkedin_post"
  | "press_release"
  | "slide_deck"
  | "video_script"
  | "playbook";

export interface OutputTypeOption {
  id: OutputTypeId;
  label: string;
  hint: string;
}

export const OUTPUT_TYPES: OutputTypeOption[] = [
  {
    id: "advisory",
    label: "Technical Advisory",
    hint: "Detailed technical bulletin with IOCs, CVEs, and MITRE ATT&CK mappings",
  },
  {
    id: "exec_summary",
    label: "Executive Brief",
    hint: "Minto Pyramid summary tailored for C-suite risk & decision-makers",
  },
  {
    id: "incident_report",
    label: "Incident Report",
    hint: "Timeline, root cause analysis, and impacted systems triage",
  },
  {
    id: "social_thread",
    label: "Social / X Thread",
    hint: "Thread breakdown optimized for character limits and high engagement",
  },
  {
    id: "linkedin_post",
    label: "LinkedIn Post",
    hint: "Structured post with key takeaways, insights, and hashtags",
  },
  {
    id: "press_release",
    label: "Public Advisory",
    hint: "Clear, non-technical public statement and safety guidelines",
  },
  {
    id: "slide_deck",
    label: "Slide Deck Outline",
    hint: "Structured presentation slides with bullet points and speaker notes",
  },
  {
    id: "video_script",
    label: "Video Script",
    hint: "Scene-by-scene script with visual cues, narrator script, and timings",
  },
  {
    id: "playbook",
    label: "Remediation Playbook",
    hint: "Step-by-step technical containment and recovery action plan",
  },
];

export function outputTypeLabel(id: OutputTypeId): string {
  return OUTPUT_TYPES.find((item) => item.id === id)?.label ?? id;
}

export interface AudienceCategory {
  id: string;
  label: string;
}

export const AUDIENCE_CATEGORIES: AudienceCategory[] = [
  { id: "technical", label: "Technical (SOC, IR, SecOps)" },
  { id: "executive", label: "Executive (C-Suite, Board)" },
  { id: "public", label: "Public & General Audience" },
  { id: "regulatory", label: "Regulators & Law Enforcement" },
  { id: "internal", label: "Internal Employees / Staff" },
];

export const TONES = [
  "Authoritative",
  "Urgent & Direct",
  "Executive & Concise",
  "Educational / Advisory",
  "Neutral & Factual",
] as const;

export const DETAIL_LEVELS = [
  "Brief / TL;DR",
  "Standard Overview",
  "Comprehensive Analysis",
  "Deep Technical Breakdown",
] as const;

export const OBJECTIVES = [
  "Threat Alert & Immediate Containment",
  "Executive Risk Assessment",
  "Incident Remediation & Recovery",
  "Public Safety & User Awareness",
  "Compliance & Regulatory Disclosure",
] as const;

export const LANGUAGES = [
  "English",
  "Hindi",
  "Spanish",
  "French",
  "German",
  "Japanese",
] as const;

export interface GenerationParams {
  audienceCategory: string;
  targetAudience?: string;
  tone: string;
  detail: string;
  objective: string;
  language: string;
}

export const DEFAULT_PARAMS: GenerationParams = {
  audienceCategory: "technical",
  targetAudience: "",
  tone: "Authoritative",
  detail: "Comprehensive Analysis",
  objective: "Threat Alert & Immediate Containment",
  language: "English",
};

export interface Citation {
  id: string;
  label: string;
  kind: "file" | "link" | "text";
}

export interface Deliverable {
  outputType: OutputTypeId;
  content: string;
  retries: number;
}

export interface Generation {
  id: string;
  createdAt: number;
  sourceText: string;
  fileNames: string[];
  links: string[];
  paramsByType: Record<OutputTypeId, GenerationParams>;
  plan?: string;
  previewsByType?: Partial<Record<OutputTypeId, string>>;
  citations: Citation[];
  deliverables: Deliverable[];
}
