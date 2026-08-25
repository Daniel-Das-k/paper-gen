import { useState } from "react";

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

interface ProductLandingPageProps {
  onLaunchDemo: () => void;
}

function ProductLogo() {
  return (
    <span className="product-logo" aria-hidden="true">
      <svg fill="none" viewBox="0 0 28 28">
        <path d="M7 3.5h10l4 4V24.5H7z" />
        <path d="M17 3.5v4h4M10.5 12h7M10.5 16h7M10.5 20h4" />
      </svg>
    </span>
  );
}

export function ProductLandingPage({ onLaunchDemo }: ProductLandingPageProps) {
  const [pattern, setPattern] = useState<PreviewPattern>("semester");
  const preview = PATTERNS[pattern];

  return (
    <div className="product-site">
      <header className="product-header">
        <div className="product-container product-header-inner">
          <a className="product-wordmark" href="#top" aria-label="REC Question Paper Studio home">
            <ProductLogo />
            <span>
              <strong>Question Paper Studio</strong>
              <small>Institutional workflow</small>
            </span>
          </a>
          <nav aria-label="Product navigation">
            <a href="#patterns">Exam patterns</a>
            <a href="#workflow">Workflow</a>
            <a href="#reliability">Reliability</a>
          </nav>
          <button className="product-header-action" onClick={onLaunchDemo} type="button">
            Launch demo
          </button>
        </div>
      </header>

      <main id="top">
        <section className="product-hero">
          <div className="product-container product-hero-grid">
            <div className="product-hero-copy">
              <p className="product-context">Prepared for an institutional demonstration</p>
              <h1>From course material to a review-ready question paper.</h1>
              <p className="product-lead">
                Generate source-grounded CAT and Semester papers, keep every exam pattern separate,
                and move each draft through Faculty, HOD and CoE review.
              </p>
              <div className="product-hero-actions">
                <button className="product-primary-action" onClick={onLaunchDemo} type="button">
                  Open local demo <span aria-hidden="true">→</span>
                </button>
                <a href="#workflow">See the workflow</a>
              </div>
              <p className="product-demo-note">Runs locally · No deployment required for the presentation</p>
            </div>

            <div className="product-preview" aria-label="Interactive question paper preview">
              <div className="product-preview-toolbar">
                <span>Paper preview</span>
                <span className="product-preview-status">Faculty review</span>
              </div>
              <div className="product-pattern-tabs" role="tablist" aria-label="Preview examination pattern">
                {(Object.keys(PATTERNS) as PreviewPattern[]).map((value) => (
                  <button
                    aria-selected={pattern === value}
                    className={pattern === value ? "product-pattern-active" : ""}
                    key={value}
                    onClick={() => setPattern(value)}
                    role="tab"
                    type="button"
                  >
                    {PATTERNS[value].short}
                  </button>
                ))}
              </div>
              <article className="product-paper">
                <div className="product-paper-heading">
                  <span>Rajalakshmi Engineering College</span>
                  <strong>{preview.title}</strong>
                  <p>CS3491 · Artificial Intelligence and Machine Learning</p>
                </div>
                <dl className="product-paper-facts">
                  <div><dt>Coverage</dt><dd>{preview.units}</dd></div>
                  <div><dt>Pattern</dt><dd>{preview.structure}</dd></div>
                  <div><dt>Duration</dt><dd>{preview.duration}</dd></div>
                  <div><dt>Maximum</dt><dd>{preview.marks}</dd></div>
                </dl>
                <div className="product-question-heading">
                  <strong>Questions</strong>
                  <span>CO · Bloom</span>
                </div>
                <ol className="product-question-list">
                  {preview.questions.map((question) => (
                    <li key={`${pattern}-${question.number}`}>
                      <span>{question.number}</span>
                      <p>{question.text}</p>
                      <small>{question.meta}</small>
                      <strong>{question.marks}</strong>
                    </li>
                  ))}
                </ol>
              </article>
            </div>
          </div>
        </section>

        <section className="product-pattern-strip" id="patterns" aria-labelledby="patterns-title">
          <div className="product-container">
            <div className="product-section-heading">
              <h2 id="patterns-title">One product, three reliable examination patterns</h2>
              <p>Each pattern keeps its own units, mark distribution and generation state.</p>
            </div>
            <div className="product-pattern-grid">
              <div>
                <strong>CAT 1</strong>
                <span>75 marks · 120 minutes</span>
                <p>Units 1 and 2, plus the prescribed CAT-I portion of Unit 3.</p>
              </div>
              <div>
                <strong>CAT 2</strong>
                <span>75 marks · 120 minutes</span>
                <p>The prescribed CAT-II portion of Unit 3, followed by Units 4 and 5.</p>
              </div>
              <div>
                <strong>End Semester</strong>
                <span>100 marks · 3 hours</span>
                <p>Units 1–5 with independent Part A, Part B and Part C requirements.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="product-section" id="workflow" aria-labelledby="workflow-title">
          <div className="product-container product-workflow-layout">
            <div className="product-section-heading product-section-heading-left">
              <h2 id="workflow-title">A workflow the examination team can follow</h2>
              <p>Every hand-off is visible, editable and recorded in the local demonstration.</p>
            </div>
            <ol className="product-workflow">
              <li><span>01</span><div><strong>Add course material</strong><p>Upload the syllabus and unit PDFs required for the selected examination.</p></div></li>
              <li><span>02</span><div><strong>Generate against the pattern</strong><p>Questions are placed according to marks, units, COs and Bloom levels.</p></div></li>
              <li><span>03</span><div><strong>Review academically</strong><p>Faculty edit the draft before HOD and CoE approval.</p></div></li>
              <li><span>04</span><div><strong>Export the approved paper</strong><p>Download the question paper, marking scheme and editable Word file.</p></div></li>
            </ol>
          </div>
        </section>

        <section className="product-section product-reliability" id="reliability" aria-labelledby="reliability-title">
          <div className="product-container product-reliability-grid">
            <div>
              <div className="product-section-heading product-section-heading-left">
                <h2 id="reliability-title">Designed for academic accountability</h2>
                <p>The system shows how a paper was produced instead of presenting AI output as a finished decision.</p>
              </div>
              <ul className="product-proof-list">
                <li><strong>Source-grounded generation</strong><span>Questions stay tied to uploaded course material.</span></li>
                <li><strong>Pattern-level isolation</strong><span>CAT 1, CAT 2 and Semester configurations are stored separately.</span></li>
                <li><strong>Human approval</strong><span>Faculty, HOD and CoE actions remain explicit.</span></li>
                <li><strong>Reviewable outputs</strong><span>Question paper, marking scheme and Word export remain aligned.</span></li>
              </ul>
            </div>
            <div className="product-audit">
              <div className="product-audit-heading"><strong>Paper readiness</strong><span>Draft</span></div>
              <dl>
                <div><dt>Exam pattern</dt><dd>End Semester · 100</dd></div>
                <div><dt>Unit coverage</dt><dd>5 of 5 units</dd></div>
                <div><dt>Course outcomes</dt><dd>CO1–CO5 mapped</dd></div>
                <div><dt>Bloom review</dt><dd>Verified per question</dd></div>
                <div><dt>Approval</dt><dd>Waiting for Faculty</dd></div>
              </dl>
              <p>Every question can be inspected and corrected before submission.</p>
            </div>
          </div>
        </section>

        <section className="product-cta">
          <div className="product-container product-cta-inner">
            <div>
              <h2>See the complete paper workflow locally.</h2>
              <p>Generate, review, approve and export without setting up a hosted environment.</p>
            </div>
            <button className="product-primary-action" onClick={onLaunchDemo} type="button">
              Launch the demo <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
      </main>

      <footer className="product-footer">
        <div className="product-container">
          <span>Question Paper Studio</span>
          <span>Local institutional demonstration</span>
        </div>
      </footer>
    </div>
  );
}
