/**
 * Built-in demonstration data, used by services/api.ts when the backend at
 * VITE_API_BASE_URL is unreachable. Everything lives in memory: papers can be
 * opened, edited, regenerated and moved through the faculty-to-HOD-to-CoE
 * approval chain, and "generation" runs as a timed simulation that produces a
 * new draft. Nothing here is persisted and nothing here talks to the network.
 */

import type {
  AnswerKeyEntry,
  BloomLevel,
  DemoActivity,
  DemoJob,
  DemoPaperRecord,
  DemoPaperStatus,
  DemoPaperSummary,
  DemoRole,
  ExamHeader,
  FullWorkflowResponse,
  MarkingCriterion,
  PaperPattern,
  SyllabusExtraction,
} from "../types/api";

const DAY_MS = 24 * 60 * 60 * 1000;
const FACULTY_DISPLAY_NAME = "Faculty User";
const CSE_DEPARTMENT = "Computer Science and Engineering";

function daysAgo(days: number, hour = 11): string {
  const date = new Date(Date.now() - days * DAY_MS);
  date.setHours(hour, (days * 17) % 60, 0, 0);
  return date.toISOString();
}

interface PaperSeed {
  id: string;
  patternId: string;
  courseCode: string;
  courseName: string;
  examLabel: string;
  year: string;
  semester: string;
  department: string;
  generatedBy: string;
  status: DemoPaperStatus;
  hodApproved: boolean;
  lastCoeAction: string;
  lastAction: string;
  createdDaysAgo: number;
  updatedDaysAgo: number;
  topics: string[];
}

const PAPER_SEEDS: PaperSeed[] = [
  {
    id: "mock-aiml-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3491",
    courseName: "Artificial Intelligence and Machine Learning",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "IV",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "draft",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Draft generated from Units 1-5",
    createdDaysAgo: 1,
    updatedDaysAgo: 0,
    topics: [
      "intelligent agents and rationality",
      "uninformed and informed search strategies",
      "constraint satisfaction problems",
      "adversarial search and game trees",
      "knowledge representation with first-order logic",
      "Bayesian networks and probabilistic reasoning",
      "supervised learning with decision trees",
      "neural network fundamentals",
      "support vector machines",
      "ensemble methods and random forests",
    ],
  },
  {
    id: "mock-cn-cat2",
    patternId: "cat-2-75",
    courseCode: "CS3591",
    courseName: "Computer Networks",
    examLabel: "CAT-II",
    year: "III Year",
    semester: "V",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "draft",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Two questions regenerated after review",
    createdDaysAgo: 3,
    updatedDaysAgo: 2,
    topics: [
      "transport layer services and multiplexing",
      "TCP congestion control",
      "UDP and connectionless transport",
      "routing algorithms and link-state protocols",
      "IPv4 addressing and subnetting",
      "network address translation",
      "application layer protocols",
      "DNS resolution",
      "socket programming primitives",
      "quality of service mechanisms",
    ],
  },
  {
    id: "mock-toc-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3452",
    courseName: "Theory of Computation",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "IV",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "submitted_to_hod",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Submitted to HOD with three candidate sets",
    createdDaysAgo: 6,
    updatedDaysAgo: 4,
    topics: [
      "deterministic finite automata",
      "nondeterminism and subset construction",
      "regular expressions and closure properties",
      "the pumping lemma for regular languages",
      "context-free grammars and derivations",
      "pushdown automata",
      "Turing machine models",
      "decidability and the halting problem",
      "reductions between problems",
      "NP-completeness",
    ],
  },
  {
    id: "mock-dbms-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3492",
    courseName: "Database Management Systems",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "IV",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "submitted_to_coe",
    hodApproved: true,
    lastCoeAction: "",
    lastAction: "HOD forwarded Set B to the CoE",
    createdDaysAgo: 10,
    updatedDaysAgo: 5,
    topics: [
      "the relational model and keys",
      "SQL joins and nested queries",
      "entity-relationship modelling",
      "functional dependencies",
      "normalization to BCNF",
      "transaction ACID properties",
      "concurrency control with locking",
      "recovery and write-ahead logging",
      "indexing with B+ trees",
      "query optimization basics",
    ],
  },
  {
    id: "mock-algo-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3401",
    courseName: "Algorithms",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "IV",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "approved",
    hodApproved: true,
    lastCoeAction: "accept",
    lastAction: "CoE approved the paper for examination",
    createdDaysAgo: 21,
    updatedDaysAgo: 12,
    topics: [
      "asymptotic notation and recurrences",
      "divide and conquer strategies",
      "dynamic programming formulation",
      "greedy algorithms and exchange arguments",
      "graph traversal with BFS and DFS",
      "shortest path algorithms",
      "minimum spanning trees",
      "network flow fundamentals",
      "string matching algorithms",
      "approximation algorithms",
    ],
  },
  {
    id: "mock-dm-cat1",
    patternId: "cat-1-75",
    courseCode: "MA3354",
    courseName: "Discrete Mathematics",
    examLabel: "CAT-I",
    year: "II Year",
    semester: "III",
    department: CSE_DEPARTMENT,
    generatedBy: "Dr. A. Farida",
    status: "submitted_to_hod",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Submitted to HOD for department review",
    createdDaysAgo: 8,
    updatedDaysAgo: 6,
    topics: [
      "propositional logic and truth tables",
      "predicates and quantifiers",
      "rules of inference",
      "mathematical induction",
      "set operations and identities",
      "relations and their properties",
      "equivalence relations and partitions",
      "functions and countability",
      "permutations and combinations",
      "the pigeonhole principle",
    ],
  },
  {
    id: "mock-dpco-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3352",
    courseName: "Digital Principles and Computer Organization",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "III",
    department: CSE_DEPARTMENT,
    generatedBy: "S. Karthik",
    status: "approved",
    hodApproved: true,
    lastCoeAction: "accept",
    lastAction: "CoE approved the paper for examination",
    createdDaysAgo: 26,
    updatedDaysAgo: 18,
    topics: [
      "boolean algebra and logic minimization",
      "combinational circuit design",
      "flip-flops and sequential circuits",
      "counters and registers",
      "instruction set architecture",
      "datapath and control design",
      "pipelining and hazards",
      "memory hierarchy and caches",
      "virtual memory",
      "I/O organization and interrupts",
    ],
  },
  {
    id: "mock-emf-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "EC3452",
    courseName: "Electromagnetic Fields",
    examLabel: "End Semester Examination",
    year: "II Year",
    semester: "IV",
    department: "Electronics and Communication Engineering",
    generatedBy: "Dr. R. Menon",
    status: "submitted_to_coe",
    hodApproved: true,
    lastCoeAction: "",
    lastAction: "HOD forwarded Set A to the CoE",
    createdDaysAgo: 12,
    updatedDaysAgo: 7,
    topics: [
      "coulomb's law and electric field intensity",
      "electric flux density and Gauss's law",
      "energy and potential in electrostatic fields",
      "conductors and dielectrics",
      "capacitance calculations",
      "Biot-Savart law and Ampere's law",
      "magnetic forces and materials",
      "Faraday's law and induced EMF",
      "Maxwell's equations",
      "plane wave propagation",
    ],
  },
  {
    id: "mock-dc-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CS3551",
    courseName: "Distributed Computing",
    examLabel: "End Semester Examination",
    year: "III Year",
    semester: "V",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "faculty_finalized",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Locked in the official format, ready to send",
    createdDaysAgo: 5,
    updatedDaysAgo: 3,
    topics: [
      "distributed system models and goals",
      "logical clocks and event ordering",
      "vector clocks",
      "global state and snapshot algorithms",
      "distributed mutual exclusion",
      "leader election algorithms",
      "consensus and agreement protocols",
      "distributed shared memory",
      "checkpointing and rollback recovery",
      "peer-to-peer overlays",
    ],
  },
  {
    id: "mock-evs-cat1",
    patternId: "cat-1-75",
    courseCode: "GE3451",
    courseName: "Environmental Sciences and Sustainability",
    examLabel: "CAT-I",
    year: "II Year",
    semester: "IV",
    department: CSE_DEPARTMENT,
    generatedBy: "Dr. S. Priya",
    status: "draft",
    hodApproved: true,
    lastCoeAction: "decline",
    lastAction: "CoE returned the paper for revision",
    createdDaysAgo: 14,
    updatedDaysAgo: 9,
    topics: [
      "ecosystem structure and function",
      "biodiversity and its conservation",
      "energy flow in ecosystems",
      "environmental pollution types",
      "solid waste management",
      "renewable energy sources",
      "water conservation and rainwater harvesting",
      "environmental impact assessment",
      "sustainable development goals",
      "climate change and mitigation",
    ],
  },
  {
    id: "mock-es-cat2",
    patternId: "cat-2-75",
    courseCode: "CS3691",
    courseName: "Embedded Systems and IoT",
    examLabel: "CAT-II",
    year: "III Year",
    semester: "VI",
    department: CSE_DEPARTMENT,
    generatedBy: FACULTY_DISPLAY_NAME,
    status: "draft",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Draft generated from Units 3-5",
    createdDaysAgo: 0,
    updatedDaysAgo: 0,
    topics: [
      "embedded processor architectures",
      "interrupt handling and timers",
      "real-time operating system concepts",
      "task scheduling policies",
      "serial communication protocols",
      "sensor interfacing",
      "IoT protocol stacks",
      "MQTT and CoAP messaging",
      "edge and cloud integration",
      "low-power design techniques",
    ],
  },
  {
    id: "mock-crypto-endsem",
    patternId: "autonomous-semester-100",
    courseCode: "CB3491",
    courseName: "Cryptography and Cyber Security",
    examLabel: "End Semester Examination",
    year: "III Year",
    semester: "V",
    department: CSE_DEPARTMENT,
    generatedBy: "Prof. K. Raghavan",
    status: "submitted_to_hod",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Submitted to HOD for department review",
    createdDaysAgo: 4,
    updatedDaysAgo: 1,
    topics: [
      "classical encryption techniques",
      "block cipher design principles",
      "the AES algorithm",
      "public key cryptography and RSA",
      "Diffie-Hellman key exchange",
      "cryptographic hash functions",
      "digital signatures",
      "authentication protocols",
      "transport layer security",
      "network attack vectors and defenses",
    ],
  },
];

/* ---------- Question and paper construction ---------- */

const BLOOM_CYCLE: BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

interface QuestionTemplate {
  text: (topic: string) => string;
  answer: (topic: string) => string;
}

const TEMPLATES: Record<BloomLevel, QuestionTemplate> = {
  remember: {
    text: (topic) => `Define ${topic} and state its essential characteristics.`,
    answer: (topic) =>
      `A precise definition of ${topic} as given in the source pages, followed by its two or three defining characteristics.`,
  },
  understand: {
    text: (topic) => `Explain ${topic} with a suitable illustrative example.`,
    answer: (topic) =>
      `An explanation of ${topic} in the candidate's own words, supported by one worked example that demonstrates the concept.`,
  },
  apply: {
    text: (topic) =>
      `Apply ${topic} to the scenario described in the question and show each step of the working.`,
    answer: (topic) =>
      `Correct selection of the method from ${topic}, systematic application to the given data, and a clearly stated result.`,
  },
  analyze: {
    text: (topic) =>
      `Compare the principal approaches within ${topic} and justify which is better suited to the stated conditions.`,
    answer: (topic) =>
      `A structured comparison across at least three criteria drawn from ${topic}, ending with a justified recommendation.`,
  },
  evaluate: {
    text: (topic) =>
      `Evaluate the effectiveness of ${topic} for the requirements given, citing the evidence for each judgement.`,
    answer: (topic) =>
      `An assessment of ${topic} against the stated requirements with explicit trade-offs and a defensible conclusion.`,
  },
  create: {
    text: (topic) =>
      `Design a complete solution using ${topic} for the given specification and justify every design decision.`,
    answer: (topic) =>
      `A coherent design grounded in ${topic}: assumptions, the design itself, and a justification linking each decision to the specification.`,
  },
};

function criteriaFor(marks: number): MarkingCriterion[] {
  if (marks <= 2) {
    return [
      { criterion: "Correct definition or statement", marks: 1 },
      { criterion: "Supporting characteristic or example", marks: marks - 1 },
    ];
  }
  if (marks === 13) {
    return [
      { criterion: "Concept identification and setup", marks: 3 },
      { criterion: "Method applied correctly, step by step", marks: 6 },
      { criterion: "Result stated and interpreted", marks: 2 },
      { criterion: "Presentation and notation", marks: 2 },
    ];
  }
  return [
    { criterion: "Problem framing and assumptions", marks: 4 },
    { criterion: "Design or solution development", marks: 7 },
    { criterion: "Justification and conclusion", marks: marks - 11 },
  ];
}

interface PatternShape {
  partAQuestions: number;
  partBPairs: number;
  hasPartC: boolean;
  totalMarks: number;
  durationMinutes: number;
}

const PATTERN_SHAPES: Record<string, PatternShape> = {
  "autonomous-semester-100": {
    partAQuestions: 10,
    partBPairs: 5,
    hasPartC: true,
    totalMarks: 100,
    durationMinutes: 180,
  },
  "cat-1-75": {
    partAQuestions: 5,
    partBPairs: 5,
    hasPartC: false,
    totalMarks: 75,
    durationMinutes: 120,
  },
  "cat-2-75": {
    partAQuestions: 5,
    partBPairs: 5,
    hasPartC: false,
    totalMarks: 75,
    durationMinutes: 120,
  },
};

const COURSE_OUTCOMES = [
  "Explain the core concepts of the course from the prescribed units",
  "Apply standard methods of the course to solve well-posed problems",
  "Analyze alternative techniques and select the appropriate one",
  "Evaluate solutions against stated constraints and criteria",
  "Design solutions for realistic problems using course techniques",
];

interface MockQuestion {
  question_id: string;
  slot_id: string;
  question_number: string;
  section_id: string;
  question_kind: string;
  question_text: string;
  marks: number;
  bloom_level: BloomLevel;
  observed_bloom_level: BloomLevel;
  bloom_matches_blueprint: boolean;
  course_outcome: string;
  course_outcome_code: string;
  visual_asset_id: null;
  accepted: boolean;
  faculty_modified: boolean;
  quality_score: number;
  quality_dimensions: {
    grounding: number;
    correctness: number;
    clarity: number;
    marks_fit: number;
    bloom_alignment: number;
    originality: number;
    answer_scheme: number;
    visual_relevance: null;
  };
  findings: Array<{
    code: string;
    severity: "error" | "warning" | "info";
    message: string;
  }>;
  topic: string;
}

function buildQuestion(
  seedId: string,
  index: number,
  questionNumber: string,
  sectionId: string,
  kind: string,
  marks: number,
  topic: string,
): MockQuestion {
  const bloom =
    marks <= 2
      ? BLOOM_CYCLE[index % 2]
      : BLOOM_CYCLE[2 + (index % 4)];
  const template = TEMPLATES[bloom];
  const outcomeIndex = index % COURSE_OUTCOMES.length;
  // Deterministic pseudo-variation so the review panel doesn't look uniform.
  const variation = ((index * 7 + seedId.length * 3) % 10) / 100;
  return {
    question_id: `${seedId}-q${index}`,
    slot_id: `${seedId}-slot${index}`,
    question_number: questionNumber,
    section_id: sectionId,
    question_kind: kind,
    question_text: template.text(topic),
    marks,
    bloom_level: bloom,
    observed_bloom_level: bloom,
    bloom_matches_blueprint: true,
    course_outcome: COURSE_OUTCOMES[outcomeIndex],
    course_outcome_code: `CO${outcomeIndex + 1}`,
    visual_asset_id: null,
    accepted: true,
    faculty_modified: false,
    quality_score: Math.round((0.86 + variation) * 100) / 100,
    quality_dimensions: {
      grounding: 0.92,
      correctness: 0.9,
      clarity: Math.round((0.85 + variation) * 100) / 100,
      marks_fit: 0.9,
      bloom_alignment: 0.88,
      originality: 0.84,
      answer_scheme: 0.9,
      visual_relevance: null,
    },
    findings: [],
    topic,
  };
}

function buildQuestions(seed: PaperSeed): MockQuestion[] {
  const shape = PATTERN_SHAPES[seed.patternId] ?? PATTERN_SHAPES["autonomous-semester-100"];
  const topics = seed.topics;
  const questions: MockQuestion[] = [];
  let index = 0;

  for (let i = 0; i < shape.partAQuestions; i += 1) {
    questions.push(
      buildQuestion(
        seed.id,
        index,
        `${i + 1}`,
        "part-a",
        "very_short_answer",
        2,
        topics[i % topics.length],
      ),
    );
    index += 1;
  }

  const partBStart = shape.partAQuestions + 1;
  for (let pair = 0; pair < shape.partBPairs; pair += 1) {
    const number = partBStart + pair;
    for (const option of ["a", "b"] as const) {
      questions.push(
        buildQuestion(
          seed.id,
          index,
          `${number}(${option})`,
          "part-b",
          "long_answer",
          13,
          topics[(pair * 2 + (option === "b" ? 1 : 0)) % topics.length],
        ),
      );
      index += 1;
    }
  }

  if (shape.hasPartC) {
    const number = partBStart + shape.partBPairs;
    for (const option of ["a", "b"] as const) {
      questions.push(
        buildQuestion(
          seed.id,
          index,
          `${number}(${option})`,
          "part-c",
          "case_study",
          15,
          topics[(index + 3) % topics.length],
        ),
      );
      index += 1;
    }
  }

  // One honest imperfection so the review panel shows a real finding.
  const flagged = questions[shape.partAQuestions + 1];
  if (flagged) {
    flagged.findings = [
      {
        code: "clarity_review",
        severity: "warning",
        message:
          "Reviewer note: the scenario framing was tightened during the automatic repair pass (attempt 2).",
      },
    ];
    flagged.quality_score = 0.78;
  }

  return questions;
}

function buildExamHeader(seed: PaperSeed): ExamHeader {
  return {
    college: "Rajalakshmi Engineering College",
    institution_line: "(An Autonomous Institution)",
    affiliation: "Affiliated to Anna University, Chennai",
    exam_title: seed.examLabel,
    year: seed.year,
    semester: seed.semester,
    branch: seed.department,
    subject_code: seed.courseCode,
    subject_name: seed.courseName,
    qp_code: `QP-${seed.courseCode}-${seed.semester}`,
    regulation: "Regulation 2021",
    common_to: seed.department,
    date: daysAgo(-14).slice(0, 10),
    register_number_boxes: 12,
  };
}

function buildResult(seed: PaperSeed): FullWorkflowResponse {
  const shape = PATTERN_SHAPES[seed.patternId] ?? PATTERN_SHAPES["autonomous-semester-100"];
  const questions = buildQuestions(seed);

  const answerKey: AnswerKeyEntry[] = questions.map((question) => ({
    question_id: question.question_id,
    question_number: question.question_number,
    section_id: question.section_id,
    marks: question.marks,
    criteria: criteriaFor(question.marks),
    answer: TEMPLATES[question.bloom_level].answer(question.topic),
  }));

  const marksByOutcome: Record<string, number> = {};
  // Either/or pairs contribute one answered question's marks.
  const answeredMarks = new Map<string, MockQuestion>();
  questions.forEach((question) => {
    const key = question.question_number.replace(/\(.+\)$/, "");
    if (!answeredMarks.has(key)) answeredMarks.set(key, question);
  });
  answeredMarks.forEach((question) => {
    const code = question.course_outcome_code;
    marksByOutcome[code] = (marksByOutcome[code] ?? 0) + question.marks;
  });

  const bloomObserved: Record<string, number> = {};
  questions.forEach((question) => {
    bloomObserved[question.bloom_level] =
      (bloomObserved[question.bloom_level] ?? 0) + 1;
  });

  const pageCount = 48;
  // Papers that have left the faculty desk carry three interchangeable
  // candidate sets, which is what the HOD compares before forwarding one.
  const hasSets =
    seed.status === "submitted_to_hod" ||
    seed.status === "submitted_to_coe" ||
    seed.status === "approved";
  const sets = hasSets
    ? (["A", "B", "C"] as const).map((label) => ({
        set_label: label,
        answer_key: answerKey,
        pdf_download_url: `#${seed.id}-set-${label.toLowerCase()}-pdf`,
        scheme_download_url: `#${seed.id}-set-${label.toLowerCase()}-scheme`,
        docx_download_url: null,
      }))
    : undefined;
  return {
    manifest: {
      document_id: `${seed.id}-doc`,
      original_filename: `${seed.courseCode.toLowerCase()}-units.pdf`,
      source_total_pages: pageCount,
      selected_page_start: 1,
      selected_page_end: pageCount,
      pages: [],
      visual_assets: [],
      quality: {
        passed: true,
        page_count: pageCount,
        text_character_count: 148_000,
        pages_without_text: [],
        warnings: [],
        errors: [],
      },
    },
    content_map: {
      subject: seed.courseName,
      topics: seed.topics.map((topic, index) => ({
        topic_id: `${seed.id}-topic${index}`,
        name: topic,
        unit: String((index % 5) + 1),
        source_pages: [index * 4 + 2, index * 4 + 3],
        supported_bloom_levels: BLOOM_CYCLE.slice(0, 4 + (index % 3)),
        evidence_chunk_ids: [`${seed.id}-ev${index}`],
      })),
      course_outcomes: COURSE_OUTCOMES,
    },
    blueprint: {
      pattern_id: seed.patternId,
      subject: seed.courseName,
      slots: questions.map((question, index) => ({
        slot_id: question.slot_id,
        question_number: question.question_number,
        section_id: question.section_id,
        marks: question.marks,
        bloom_level: question.bloom_level,
        requested_bloom_level: question.bloom_level,
        question_kind: question.question_kind,
        topic_id: `${seed.id}-topic${index % seed.topics.length}`,
        unit: String((index % 5) + 1),
        facet: null,
        source_pages: [index * 2 + 2],
        evidence_chunk_ids: [`${seed.id}-ev${index % seed.topics.length}`],
        requires_visual: false,
        visual_asset_id: null,
      })),
      warnings: [],
    },
    pdf_download_url: "#mock-paper-pdf",
    scheme_download_url: "#mock-scheme-pdf",
    docx_download_url: null,
    answer_key: answerKey,
    sets,
    cross_set_warnings: [],
    selected_set_label: seed.hodApproved ? "B" : null,
    paper: {
      title: `${seed.courseCode} - ${seed.examLabel}`,
      set_label: seed.hodApproved ? "B" : null,
      subject: seed.courseName,
      subject_family: "computing",
      duration_minutes: shape.durationMinutes,
      total_marks: shape.totalMarks,
      exam_header: buildExamHeader(seed),
      requires_human_approval: true,
      publication_ready: true,
      course_outcome_coverage: {
        marks_by_outcome: marksByOutcome,
        unmapped_marks: 0,
        total_marks: shape.totalMarks,
      },
      bloom_summary: {
        requested: bloomObserved,
        observed: bloomObserved,
        deviations: 0,
        total: questions.length,
        unverified: 0,
      },
      questions: questions.map(({ topic: _topic, ...question }) => question),
    },
  };
}

function buildActivities(seed: PaperSeed): DemoActivity[] {
  const activities: DemoActivity[] = [
    {
      actor_role: "faculty",
      action: "generated",
      comment: "Draft generated from the uploaded unit material.",
      created_at: daysAgo(seed.createdDaysAgo, 10),
    },
  ];
  const reached = (status: DemoPaperStatus) => {
    const order: DemoPaperStatus[] = [
      "draft",
      "faculty_finalized",
      "submitted_to_hod",
      "submitted_to_coe",
      "approved",
    ];
    return order.indexOf(seed.status) >= order.indexOf(status) || seed.hodApproved;
  };
  if (reached("faculty_finalized")) {
    activities.push({
      actor_role: "faculty",
      action: "finalize",
      comment: "Locked in the official format.",
      created_at: daysAgo(seed.updatedDaysAgo + 2, 12),
    });
  }
  if (reached("submitted_to_hod")) {
    activities.push({
      actor_role: "faculty",
      action: "submit",
      comment: "Submitted with three candidate sets.",
      created_at: daysAgo(seed.updatedDaysAgo + 1, 15),
    });
  }
  if (seed.hodApproved) {
    activities.push({
      actor_role: "hod",
      action: "approve",
      comment: "Compared candidate sets and forwarded Set B.",
      created_at: daysAgo(seed.updatedDaysAgo, 16),
    });
  }
  if (seed.lastCoeAction === "accept") {
    activities.push({
      actor_role: "coe",
      action: "accept",
      comment: "Cleared for the examination.",
      created_at: daysAgo(seed.updatedDaysAgo, 17),
    });
  }
  if (seed.lastCoeAction === "decline") {
    activities.push({
      actor_role: "coe",
      action: "decline",
      comment: "Two Part B questions overlap Unit 3 too heavily; please rebalance.",
      created_at: daysAgo(seed.updatedDaysAgo, 17),
    });
  }
  return activities;
}

function buildRecord(seed: PaperSeed): DemoPaperRecord {
  return {
    id: seed.id,
    pattern_id: seed.patternId,
    subject: seed.courseName,
    course_code: seed.courseCode,
    course_name: seed.courseName,
    exam_label: seed.examLabel,
    year: seed.year,
    semester: seed.semester,
    department: seed.department,
    generated_by: seed.generatedBy,
    last_action: seed.lastAction,
    hod_approved: seed.hodApproved,
    last_coe_action: seed.lastCoeAction,
    status: seed.status,
    created_at: daysAgo(seed.createdDaysAgo, 10),
    updated_at: daysAgo(seed.updatedDaysAgo, 15),
    result: buildResult(seed),
    activities: buildActivities(seed),
  };
}

/* ---------- In-memory store ---------- */

const store: Map<string, DemoPaperRecord> = new Map(
  PAPER_SEEDS.map((seed) => [seed.id, buildRecord(seed)]),
);

function summarize(record: DemoPaperRecord): DemoPaperSummary {
  const { result: _result, activities: _activities, ...summary } = record;
  return summary;
}

function requirePaper(paperId: string): DemoPaperRecord {
  const record = store.get(paperId);
  if (!record) {
    throw new Error(`Paper ${paperId} was not found in the demo data.`);
  }
  return record;
}

function touch(record: DemoPaperRecord): void {
  record.updated_at = new Date().toISOString();
}

export function mockListPapers(): DemoPaperSummary[] {
  return [...store.values()]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .map(summarize);
}

export function mockGetPaper(paperId: string): DemoPaperRecord {
  return requirePaper(paperId);
}

export function mockEditQuestion(
  paperId: string,
  questionId: string,
  edit: {
    question_text: string;
    answer: string;
    criteria: MarkingCriterion[];
  },
): DemoPaperRecord {
  const record = requirePaper(paperId);
  const question = record.result.paper.questions.find(
    (candidate) => candidate.question_id === questionId,
  );
  if (!question) {
    throw new Error("That question no longer exists in the demo paper.");
  }
  question.question_text = edit.question_text;
  question.faculty_modified = true;
  const keyEntry = record.result.answer_key?.find(
    (entry) => entry.question_id === questionId,
  );
  if (keyEntry) {
    keyEntry.answer = edit.answer;
    keyEntry.criteria = edit.criteria;
  }
  record.last_action = "Faculty edited a question inline";
  touch(record);
  return record;
}

export function mockRegenerateQuestion(
  paperId: string,
  questionId: string,
): DemoPaperRecord {
  const record = requirePaper(paperId);
  const question = record.result.paper.questions.find(
    (candidate) => candidate.question_id === questionId,
  );
  if (!question) {
    throw new Error("That question no longer exists in the demo paper.");
  }
  question.question_text = `${question.question_text.replace(/\.$/, "")}, using a fresh self-contained scenario drawn from the same source pages.`;
  question.faculty_modified = false;
  question.quality_score = 0.9;
  question.findings = [];
  record.last_action = "One question regenerated against its evidence";
  touch(record);
  return record;
}

export function mockUpdateHeader(
  paperId: string,
  header: ExamHeader,
): DemoPaperRecord {
  const record = requirePaper(paperId);
  record.result.paper.exam_header = header;
  record.course_code = header.subject_code;
  record.course_name = header.subject_name;
  record.year = header.year;
  record.semester = header.semester;
  record.last_action = "Faculty updated the examination details";
  touch(record);
  return record;
}

export function mockTransitionPaper(
  paperId: string,
  actorRole: DemoRole,
  action: "finalize" | "submit" | "approve" | "return" | "accept" | "decline",
  comment: string,
  selectedSetLabel?: string,
): DemoPaperRecord {
  const record = requirePaper(paperId);
  const transitions: Record<string, () => void> = {
    "faculty:finalize": () => {
      record.status = "faculty_finalized";
      record.last_action = "Locked in the official format";
    },
    "faculty:submit": () => {
      record.status = "submitted_to_hod";
      record.last_action = "Submitted to HOD";
    },
    "hod:approve": () => {
      record.status = "submitted_to_coe";
      record.hod_approved = true;
      record.result.selected_set_label = selectedSetLabel ?? "A";
      record.last_action = `HOD forwarded Set ${selectedSetLabel ?? "A"} to the CoE`;
    },
    "hod:return": () => {
      record.status = "draft";
      record.last_action = "HOD returned the paper to faculty";
    },
    "coe:accept": () => {
      record.status = "approved";
      record.last_coe_action = "accept";
      record.last_action = "CoE approved the paper for examination";
    },
    "coe:decline": () => {
      record.status = "draft";
      record.last_coe_action = "decline";
      record.last_action = "CoE returned the paper for revision";
    },
  };
  const apply = transitions[`${actorRole}:${action}`];
  if (!apply) {
    throw new Error(`A ${actorRole} account cannot perform "${action}" here.`);
  }
  apply();
  record.activities.push({
    actor_role: actorRole,
    action,
    comment,
    created_at: new Date().toISOString(),
  });
  touch(record);
  return record;
}

/* ---------- Simulated generation jobs ---------- */

const JOB_DURATION_MS = 14_000;
const JOB_STAGES: Array<[number, string]> = [
  [0, "Inspecting the uploaded unit PDFs"],
  [15, "Analyzing source pages and mapping topics"],
  [35, "Generating Part A"],
  [55, "Generating Part B and Part C"],
  [75, "Independent review pass"],
  [90, "Assembling the paper and scheme of evaluation"],
];

interface MockJobState {
  job: DemoJob;
  startedAt: number;
  seed: PaperSeed;
}

const jobs = new Map<string, MockJobState>();

export function mockCreateJob(
  patternId: string,
  details: {
    courseCode: string;
    courseName: string;
    year: string;
    semester: string;
  },
  generatedBy: string,
): DemoJob {
  const id = `mock-job-${Date.now()}`;
  const courseName = details.courseName.trim() || "Untitled Course";
  const seed: PaperSeed = {
    id: `mock-paper-${Date.now()}`,
    patternId,
    courseCode: details.courseCode.trim() || "NEW101",
    courseName,
    examLabel:
      patternId === "cat-1-75"
        ? "CAT-I"
        : patternId === "cat-2-75"
          ? "CAT-II"
          : "End Semester Examination",
    year: details.year.trim() || "II Year",
    semester: details.semester.trim() || "IV",
    department: CSE_DEPARTMENT,
    generatedBy,
    status: "draft",
    hodApproved: false,
    lastCoeAction: "",
    lastAction: "Draft generated from the uploaded unit material",
    createdDaysAgo: 0,
    updatedDaysAgo: 0,
    topics: PAPER_SEEDS[0].topics,
  };
  const now = new Date().toISOString();
  const job: DemoJob = {
    id,
    status: "queued",
    stage: JOB_STAGES[0][1],
    progress: 0,
    error: null,
    paper_id: null,
    created_at: now,
    updated_at: now,
  };
  jobs.set(id, { job, startedAt: Date.now(), seed });
  return { ...job };
}

export function mockGetJob(jobId: string): DemoJob {
  const state = jobs.get(jobId);
  if (!state) {
    throw new Error("That generation job is not part of the demo session.");
  }
  const elapsed = Date.now() - state.startedAt;
  const progress = Math.min(100, Math.round((elapsed / JOB_DURATION_MS) * 100));
  if (progress >= 100) {
    if (!state.job.paper_id) {
      const record = buildRecord(state.seed);
      record.created_at = new Date().toISOString();
      record.updated_at = record.created_at;
      store.set(record.id, record);
      state.job.paper_id = record.id;
    }
    state.job.status = "completed";
    state.job.progress = 100;
    state.job.stage = "Draft ready for faculty review";
  } else {
    state.job.status = "running";
    state.job.progress = progress;
    state.job.stage =
      [...JOB_STAGES].reverse().find(([threshold]) => progress >= threshold)?.[1] ??
      JOB_STAGES[0][1];
  }
  state.job.updated_at = new Date().toISOString();
  return { ...state.job };
}

/* ---------- Static lookups ---------- */

export function mockPatterns(): PaperPattern[] {
  return [
    {
      pattern_id: "cat-1-75",
      name: "CAT-I - 75 marks - 120 minutes",
      duration_minutes: 120,
      total_marks: 75,
      sections: [],
    },
    {
      pattern_id: "cat-2-75",
      name: "CAT-II - 75 marks - 120 minutes",
      duration_minutes: 120,
      total_marks: 75,
      sections: [],
    },
    {
      pattern_id: "autonomous-semester-100",
      name: "End-semester - 100 marks - 3 hours",
      duration_minutes: 180,
      total_marks: 100,
      sections: [],
    },
  ];
}

export function mockExtractSyllabus(): SyllabusExtraction {
  return {
    subject_code: "CS3491",
    subject_name: "Artificial Intelligence and Machine Learning",
    regulation: "Regulation 2021",
    units: [
      { number: "1", title: "Problem Solving", topics: "Agents, search strategies, heuristics" },
      { number: "2", title: "Probabilistic Reasoning", topics: "Bayesian inference, exact and approximate methods" },
      { number: "3", title: "Supervised Learning", topics: "Regression, decision trees, SVM" },
      { number: "4", title: "Ensemble Techniques", topics: "Bagging, boosting, unsupervised learning" },
      { number: "5", title: "Neural Networks", topics: "Perceptrons, backpropagation, deep architectures" },
    ],
    course_outcomes: COURSE_OUTCOMES,
    extraction_confident: true,
    problem: null,
  };
}
