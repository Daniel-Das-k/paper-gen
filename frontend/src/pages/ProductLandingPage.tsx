import { useEffect, useState, type CSSProperties } from "react";

import { ThemeToggle } from "../components/layout/ThemeToggle";
import { DrawCheck, QpMark } from "../components/icons/Icons";

type PreviewPattern = "cat1" | "cat2" | "semester";

const PATTERNS: Record<
  PreviewPattern,
  {
    short: string;
    title: string;
    marks: string;
    duration: string;
    units: string;
    structure: string;
    questions: Array<{ number: string; text: string; meta: string; marks: string }>;
  }
> = {
  cat1: {
    short: "CAT 1",
    title: "Continuous Assessment Test I",
    marks: "75 marks",
    duration: "120 minutes",
    units: "Units 1, 2 and CAT-I portion of Unit 3",
    structure: "Combined Part A followed by combined Part B",
    questions: [
      { number: "1", text: "Define an intelligent agent and state its principal characteristics.", meta: "CO1 · Understand", marks: "2" },
      { number: "2", text: "Compare breadth-first and depth-first search strategies.", meta: "CO1 · Analyse", marks: "2" },
      { number: "7(a)", text: "Apply informed search to solve the given state-space problem.", meta: "CO2 · Apply", marks: "13" },
    ],
  },
  cat2: {
    short: "CAT 2",
    title: "Continuous Assessment Test II",
    marks: "75 marks",
    duration: "120 minutes",
    units: "CAT-II portion of Unit 3 and Units 4–5",
    structure: "Combined Part A followed by combined Part B",
    questions: [
      { number: "1", text: "State the purpose of a knowledge representation scheme.", meta: "CO3 · Remember", marks: "2" },
      { number: "2", text: "Differentiate supervised and unsupervised learning.", meta: "CO4 · Analyse", marks: "2" },
      { number: "7(a)", text: "Evaluate a learning model using the supplied performance evidence.", meta: "CO4 · Evaluate", marks: "13" },
    ],
  },
  semester: {
    short: "Semester",
    title: "End Semester Examination",
    marks: "100 marks",
    duration: "3 hours",
    units: "Units 1–5",
    structure: "Part A 20 · Part B 65 · Part C 15",
    questions: [
      { number: "1", text: "Identify two properties of a rational agent.", meta: "CO1 · Remember", marks: "2" },
      { number: "2", text: "Explain the role of heuristics in problem solving.", meta: "CO2 · Understand", marks: "2" },
      { number: "11(a)", text: "Design and justify a suitable solution for the given application.", meta: "CO5 · Create", marks: "13" },
    ],
  },
};

const FEATURE_CARDS = [
  {
    title: "Evidence attached to every question",
    body: "The uploaded pages define the permitted concepts and terminology. Each question carries the source excerpt it was written from, so reviewers check facts, not vibes.",
    visual: "evidence",
  },
  {
    title: "An independent review pass",
    body: "Every part is generated, then reviewed by a second cold-temperature pass. Deterministic gates check marks, Bloom levels, duplicates, figures and structure.",
    visual: "review",
  },
  {
    title: "Answer-free by construction",
    body: "The question paper never contains an answer. Marking schemes travel beside it for faculty and in the separate scheme of evaluation for the exam cell.",
    visual: "answerfree",
  },
] as const;

const GATE_ITEMS = [
  { label: "Marks total", note: "Every part sums exactly" },
  { label: "Evidence check", note: "Excerpt behind each question" },
  { label: "Bloom verified", note: "Level matched to the source" },
  { label: "Duplicate scan", note: "Semantic, whole-paper" },
  { label: "Figure gate", note: "Verified textbook visuals only" },
  { label: "Either / or", note: "Choice structure enforced" },
  { label: "CO mapping", note: "Marks reported per outcome" },
  { label: "Repair ladder", note: "4 attempts, then redesign" },
] as const;

const PROMPT_BUBBLES = [
  "CAT-I for CS3491 — Units 1, 2 and the CAT-I portion of Unit 3, 75 marks.",
  "End semester, 100 marks, Units 1–5. Three equivalent sets for the CoE.",
] as const;

const WORKFLOW_STEPS = [
  {
    number: "1",
    title: "Upload the unit PDFs",
    body: "Page ranges physically isolate the syllabus before any model call.",
  },
  {
    number: "2",
    title: "The paper is written",
    body: "Grounded generation, independent review, per-question repair.",
  },
  {
    number: "3",
    title: "Faculty review inline",
    body: "Edit wording and marking criteria. Regenerate one question at a time.",
  },
  {
    number: "4",
    title: "HOD and CoE sign off",
    body: "Paper, scheme and Word export stay aligned through approval.",
  },
] as const;

const TESTIMONIALS = [
  {
    name: "Dr. S. Priya",
    role: "Assistant Professor, CSE",
    quote:
      "Setting a CAT used to take my weekend. Now I spend the hour where it matters — reading each question against the evidence and fixing the two I don't like.",
  },
  {
    name: "Prof. K. Raghavan",
    role: "Head of Department, ECE",
    quote:
      "I can finally see why a question exists. The excerpt is right there. Approving a paper stopped being an act of faith.",
  },
  {
    name: "Dr. M. Vasanthi",
    role: "Controller of Examinations",
    quote:
      "The scheme of evaluation arrives with the paper, mark-wise, in the format valuers actually use. That alone justified the pilot.",
  },
  {
    name: "S. Karthik",
    role: "Assistant Professor, IT",
    quote:
      "The Bloom mapping is honest. When the source can't support a 'Create' question, it doesn't pretend. That's rarer than it should be.",
  },
  {
    name: "Dr. A. Farida",
    role: "Professor, Mathematics",
    quote:
      "Three equivalent sets, none of them clones. The facet system genuinely varies what each question asks for.",
  },
  {
    name: "R. Devi",
    role: "Exam cell coordinator",
    quote:
      "Nothing reaches me unsigned, and nothing in the paper leaks an answer. The audit trail is the feature nobody advertises.",
  },
] as const;

interface ProductLandingPageProps {
  onLaunchDemo: () => void;
}

function PaperArtifact({ pattern }: { pattern: PreviewPattern }) {
  const preview = PATTERNS[pattern];
  return (
    <article className="lp-sheet" aria-label={`${preview.title} preview`}>
      <div className="lp-sheet-regno">
        <span>Reg. No.</span>
        <span className="lp-sheet-boxes" aria-hidden="true">
          {Array.from({ length: 12 }, (_, index) => (
            <i key={index} />
          ))}
        </span>
      </div>
      <header className="lp-sheet-masthead">
        <div>
          <strong>Rajalakshmi Engineering College</strong>
          <span>(An Autonomous Institution)</span>
        </div>
        <dl>
          <div>
            <dt>Exam</dt>
            <dd>{preview.title}</dd>
          </div>
          <div>
            <dt>Course</dt>
            <dd>CS3491 · Artificial Intelligence and Machine Learning</dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>{preview.units}</dd>
          </div>
          <div>
            <dt>Time / Max</dt>
            <dd>
              {preview.duration} · {preview.marks}
            </dd>
          </div>
        </dl>
      </header>
      <p className="lp-sheet-structure">{preview.structure}</p>
      <ol className="lp-sheet-questions">
        {preview.questions.map((question) => (
          <li key={`${pattern}-${question.number}`}>
            <span className="lp-sheet-qno">{question.number}.</span>
            <p>{question.text}</p>
            <span className="lp-sheet-qmeta">{question.meta}</span>
            <strong>{question.marks}</strong>
          </li>
        ))}
      </ol>
      <footer className="lp-sheet-stamp">
        <span className="lp-chip lp-chip-amber">Awaiting faculty review</span>
        <span>Page 1 of 3</span>
      </footer>
    </article>
  );
}

function FeatureVisual({ kind }: { kind: (typeof FEATURE_CARDS)[number]["visual"] }) {
  if (kind === "evidence") {
    return (
      <div className="lp-card-visual" aria-hidden="true">
        <div className="lp-vis-lines">
          <i style={{ width: "82%" }} />
          <i style={{ width: "94%" }} />
          <i className="lp-vis-highlight" style={{ width: "70%" }} />
          <i style={{ width: "88%" }} />
        </div>
        <span className="lp-vis-cite">p. 214 · §5.3</span>
      </div>
    );
  }
  if (kind === "review") {
    return (
      <div className="lp-card-visual" aria-hidden="true">
        <ul className="lp-vis-checks">
          <li><DrawCheck className="lp-vis-tick-svg" />Marks total 100</li>
          <li><DrawCheck className="lp-vis-tick-svg" />Bloom level verified</li>
          <li><DrawCheck className="lp-vis-tick-svg lp-vis-tick-warn" />Q7(b) repaired · attempt 2</li>
        </ul>
      </div>
    );
  }
  return (
    <div className="lp-card-visual" aria-hidden="true">
      <div className="lp-vis-docs">
        <div className="lp-vis-doc">
          <span>Question paper</span>
          <em>answer-free</em>
        </div>
        <div className="lp-vis-doc lp-vis-doc-scheme">
          <span>Scheme of evaluation</span>
          <em>faculty only</em>
        </div>
      </div>
    </div>
  );
}

export function ProductLandingPage({ onLaunchDemo }: ProductLandingPageProps) {
  const [pattern, setPattern] = useState<PreviewPattern>("semester");

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.documentElement.classList.add("lp-reveal-ready");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "-40px 0px" },
    );
    document
      .querySelectorAll("[data-reveal]")
      .forEach((element) => observer.observe(element));
    return () => {
      observer.disconnect();
      document.documentElement.classList.remove("lp-reveal-ready");
    };
  }, []);

  return (
    <div className="lp">
      <header className="lp-header">
        <div className="lp-frame lp-header-inner">
          <a className="lp-wordmark" href="#top" aria-label="Question Paper Studio home">
            <span className="lp-wordmark-mark" aria-hidden="true">
              <QpMark />
            </span>
            <span>
              <strong>QP Studio</strong>
              <small>Rajalakshmi Engineering College</small>
            </span>
          </a>
          <nav aria-label="Product navigation">
            <a href="#grounded">Grounding</a>
            <a href="#gates">Guarantees</a>
            <a href="#workflow">Workflow</a>
            <a href="#voices">Voices</a>
          </nav>
          <div className="lp-header-actions">
            <ThemeToggle />
            <button className="lp-btn-primary" onClick={onLaunchDemo} type="button">
              Open the studio
            </button>
          </div>
        </div>
      </header>

      <main id="top">
        <section className="lp-hero">
          <span className="lp-ghost" aria-hidden="true">QP STUDIO</span>
          <div className="lp-frame lp-hero-inner">
            <p className="lp-badge enter-up">
              <i aria-hidden="true" /> Runs locally · faculty stay in control
            </p>
            <h1
              className="lp-display enter-up"
              style={{ "--arc-delay": "90ms" } as CSSProperties}
            >
              The question paper,
              <br />
              written from the{" "}
              <span className="lp-scribble">
                textbook
                <svg
                  aria-hidden="true"
                  className="lp-scribble-svg"
                  fill="none"
                  preserveAspectRatio="none"
                  viewBox="0 0 140 10"
                >
                  <path
                    className="svg-draw lp-scribble-path"
                    d="M2 7.2 C 28 11.4, 72 1.6, 138 6.4"
                    pathLength={1}
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeWidth="1.8"
                  />
                </svg>
              </span>
            </h1>
            <p
              className="lp-lead enter-up"
              style={{ "--arc-delay": "180ms" } as CSSProperties}
            >
              Upload the unit PDFs and get a review-ready CAT or semester paper —
              every question grounded in the source, every mark accounted for.
            </p>
            <div
              className="lp-hero-actions enter-up"
              style={{ "--arc-delay": "270ms" } as CSSProperties}
            >
              <button className="lp-btn-primary lp-btn-lg" onClick={onLaunchDemo} type="button">
                Open the studio <span aria-hidden="true">→</span>
              </button>
              <a className="lp-btn-ghost lp-btn-lg" href="#workflow">
                See how it works
              </a>
            </div>

            <div
              className="lp-hero-artifact enter-up"
              style={{ "--arc-delay": "380ms" } as CSSProperties}
            >
              <div className="lp-window">
                <div className="lp-window-bar">
                  <span className="lp-window-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="lp-window-title">CS3491 · draft paper</span>
                  <span className="lp-window-status">Draft</span>
                </div>
                <div className="lp-window-toolbar">
                  <div
                    className="lp-pattern-tabs"
                    role="tablist"
                    aria-label="Examination pattern"
                  >
                    {(Object.keys(PATTERNS) as PreviewPattern[]).map((value) => (
                      <button
                        aria-selected={pattern === value}
                        className={pattern === value ? "lp-tab-active" : ""}
                        key={value}
                        onClick={() => setPattern(value)}
                        role="tab"
                        type="button"
                      >
                        {PATTERNS[value].short}
                      </button>
                    ))}
                  </div>
                  <span className="lp-window-meta">
                    {PATTERNS[pattern].marks} · {PATTERNS[pattern].duration}
                  </span>
                </div>
                <div className="lp-window-body">
                  <PaperArtifact pattern={pattern} />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section" id="grounded">
          <div className="lp-frame">
            <div className="lp-section-split" data-reveal>
              <h2 className="lp-display-2">
                Grounded generation for your question papers
              </h2>
              <p>
                The model never invents a syllabus. Source pages set the scope,
                deterministic gates check the output, and faculty hold the pen at
                every step that matters.
              </p>
            </div>
            <div className="lp-feature-grid">
              {FEATURE_CARDS.map((card, index) => (
                <article
                  className="lp-card"
                  data-reveal
                  key={card.title}
                  style={{ "--arc-delay": `${index * 90}ms` } as CSSProperties}
                >
                  <FeatureVisual kind={card.visual} />
                  <h3>{card.title}</h3>
                  <p>{card.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-band" id="gates">
          <div className="lp-frame">
            <div className="lp-section-split" data-reveal>
              <h2 className="lp-display-2">
                Every question passes the same gates
              </h2>
              <p>
                A paper isn't publishable because it reads well. It's publishable
                because it cleared each of these checks — and the ones that fail
                are repaired individually, never papered over.
              </p>
            </div>
            <ul className="lp-gate-grid" data-reveal>
              {GATE_ITEMS.map((gate) => (
                <li key={gate.label}>
                  <DrawCheck className="lp-gate-mark" />
                  <span>
                    <strong>{gate.label}</strong>
                    <small>{gate.note}</small>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section" id="workflow">
          <div className="lp-frame">
            <div className="lp-prompt-head" data-reveal>
              <h2 className="lp-display-2">Start from the syllabus</h2>
              <div className="lp-pill-tabs" aria-hidden="true">
                <span className="lp-pill-active">CAT</span>
                <span>End semester</span>
              </div>
            </div>
            <div className="lp-bubbles" data-reveal>
              {PROMPT_BUBBLES.map((bubble) => (
                <p className="lp-bubble" key={bubble}>
                  {bubble}
                </p>
              ))}
            </div>
            <ol className="lp-steps">
              {WORKFLOW_STEPS.map((step, index) => (
                <li
                  data-reveal
                  key={step.number}
                  style={{ "--arc-delay": `${index * 80}ms` } as CSSProperties}
                >
                  <span className="lp-step-no">{step.number}</span>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-section lp-voices" id="voices">
          <div className="lp-frame">
            <h2 className="lp-display-2 lp-center" data-reveal>
              What the pilot rooms are saying
            </h2>
            <div className="lp-quote-grid">
              {TESTIMONIALS.map((entry, index) => (
                <figure
                  className="lp-quote"
                  data-reveal
                  key={entry.name}
                  style={{ "--arc-delay": `${(index % 3) * 90}ms` } as CSSProperties}
                >
                  <figcaption>
                    <span className="lp-quote-avatar" aria-hidden="true">
                      {entry.name.replace(/^(Dr\.|Prof\.)\s*/, "").charAt(0)}
                    </span>
                    <span>
                      <strong>{entry.name}</strong>
                      <small>{entry.role}</small>
                    </span>
                  </figcaption>
                  <blockquote>{entry.quote}</blockquote>
                </figure>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-cta">
          <span className="lp-ghost lp-ghost-cta" aria-hidden="true">QP STUDIO</span>
          <div className="lp-frame lp-cta-inner" data-reveal>
            <h2 className="lp-display">What will your first paper cover?</h2>
            <div className="lp-cta-actions">
              <button className="lp-btn-primary lp-btn-lg" onClick={onLaunchDemo} type="button">
                Open the studio <span aria-hidden="true">→</span>
              </button>
              <a className="lp-btn-ghost lp-btn-lg" href="#grounded">
                Read how it's grounded
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-frame lp-footer-grid">
          <div className="lp-footer-brand">
            <span className="lp-wordmark-mark" aria-hidden="true">QP</span>
            <strong>QP Studio</strong>
            <p>Source-grounded question papers for the examination cell.</p>
          </div>
          <nav aria-label="Product links">
            <span>Product</span>
            <a href="#grounded">Grounding</a>
            <a href="#gates">Validation gates</a>
            <a href="#workflow">Workflow</a>
          </nav>
          <nav aria-label="Governance links">
            <span>Governance</span>
            <a href="#gates">Approval chain</a>
            <a href="#gates">Scheme of evaluation</a>
            <a href="#voices">Pilot voices</a>
          </nav>
          <nav aria-label="Institution links">
            <span>Institution</span>
            <a href="#top">Rajalakshmi Engineering College</a>
            <a href="#top">Examination cell</a>
          </nav>
        </div>
        <div className="lp-frame lp-footer-bottom">
          <span>Question Paper Studio</span>
          <span>Local institutional demonstration · not production authentication</span>
        </div>
      </footer>
    </div>
  );
}
