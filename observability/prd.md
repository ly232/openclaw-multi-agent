# OpenClaw Observability Dashboard

## Product Requirements Document (PRD)

## 1. Overview

The OpenClaw Observability Dashboard is a standalone web application that provides operational visibility into an OpenClaw multi-agent system.

The dashboard allows operators to understand:

* who is using the system;
* which agents are being invoked;
* how requests are routed;
* how much tokens and cost are consumed;
* why a response was generated;
* whether agent behavior is improving over time.

The target architecture:

```text
                         WeChat

                            |

                            v

                   OpenClaw Gateway

                            |

                            v

                 Orchestrator Agent

                    /       |       \

                   /        |        \

                  v         v         v

             Coding     Research    General
              Agent       Agent      Agent
```

The dashboard should provide visibility across the entire lifecycle:

```text
User Request

    |

    v

Session

    |

    v

Agent Routing

    |

    v

Agent Execution

    |

    v

Final Response

    |

    v

Quality Evaluation
```

---

# 2. Goals

## Functional Goals

The dashboard should answer:

### Usage

* Which WeChat accounts use the system?
* Which agents consume the most resources?
* How many interactions happen daily?

### Debugging

* Why did a particular response happen?
* Which agents participated?
* What tools were called?
* What was the execution timeline?

### Quality

* Was the response correct?
* Was routing effective?
* Did multi-agent collaboration help?

### Evolution

* Did a prompt change improve quality?
* Did an agent regression occur?

---

# 3. Non-Goals

The dashboard is not responsible for:

* replacing OpenClaw Gateway;
* executing agents;
* managing prompts;
* routing requests.

OpenClaw remains responsible for execution.

The dashboard is an observability and evaluation layer.

---

# 4. High-Level Architecture

```text
OpenClaw Runtime

       |

       v

Log Collector

       |

       v

Trace Normalizer

       |

       v

Analytics Database

       |

       v

Dashboard Frontend
```

---

# 5. Data Collection Architecture

## Log Collector

The collector reads OpenClaw runtime artifacts.

Example:

```text
~/.openclaw/

agents/

  <agent_name>/

      sessions/

          <session_id>.trajectory.jsonl
```

Responsibilities:

* monitor new logs;
* process incremental updates;
* avoid duplicate ingestion;
* handle schema changes.

---

# 6. Trace Normalization

Different model providers expose different metadata.

Examples:

* OpenAI;
* DeepSeek;
* Anthropic;
* local models.

The system normalizes provider-specific traces into a common format.

---

# 7. Interaction Data Model

Each user interaction becomes a normalized record.

Example:

```yaml
interaction_id:

timestamp:

channel:

account_id:

session_id:


user_message:


assistant_response:


root_agent:


agents_involved:

  - orchestrator

  - coding


usage:

  input_tokens:

  output_tokens:

  total_tokens:


latency_ms:


status:
```

---

# 8. Execution Trace Model

The dashboard should display execution traces.

Do not label this as raw chain-of-thought.

The trace represents observable execution events:

```text
Interaction

|
+-- User Message
|
+-- Orchestrator Decision
|
+-- Agent Invocation
|
+-- Tool Calls
|
+-- Model Response
|
+-- Final Response
```

Possible trace fields:

* timestamp;
* agent;
* model;
* tool;
* token usage;
* latency;
* status;
* metadata.

---

# 9. Frontend Architecture

## Technology Choice

Recommended stack:

```yaml
framework:
  React

language:
  TypeScript

styling:
  Tailwind CSS

components:
  shadcn/ui

tables:
  TanStack Table

charts:
  Recharts

graph:
  React Flow
```

---

# 10. UI Design Principles

The dashboard should resemble modern observability platforms.

Priorities:

* high information density;
* fast navigation;
* interactive filtering;
* responsive layout;
* dark mode support.

---

# 11. Application Layout

```text
+------------------------------------------------+

| OpenClaw Observability                         |

+------------------------------------------------+

| Sidebar                                        |
|                                                |
| Dashboard                                      |
| Accounts                                       |
| Agents                                         |
| Messages                                       |
| Evaluations                                    |
| Settings                                       |

+------------------------------------------------+

| Main Content                                   |

+------------------------------------------------+
```

---

# 12. Homepage

The homepage provides system-level visibility.

---

## System Summary Cards

Display:

```text
Last 7 days

Interactions:
12,430

Tokens:
82M

Estimated Cost:
$430

Average Latency:
4.2s

Failures:
0.5%

Multi-Agent Requests:
18%
```

---

# 13. Top WeChat Accounts

Display top-N accounts ranked by token usage.

Requirements:

* configurable N;
* default: 10;
* maximum: 100;
* pagination;
* default window: last 7 days.

Table:

| Account | Messages | Tokens | Cost |
| ------- | -------- | ------ | ---- |
| user-a  | 800      | 2M     | $20  |

Click:

Account View.

---

# 14. Top Agents

Display top-N agents ranked by usage.

Table:

| Agent  | Requests | Tokens | Latency |
| ------ | -------- | ------ | ------- |
| Coding | 1200     | 18M    | 3.5s    |

Click:

Agent View.

---

# 15. Account View

Shows one user's interaction history.

A message means:

```text
User Message

+

Complete Assistant Response
```

Requirements:

* pagination;
* default 10;
* maximum 100;
* last 7 days.

Table:

| Time  | Message      | Agents | Tokens |
| ----- | ------------ | ------ | ------ |
| 10:30 | Debug Python | Coding | 2200   |

---

# 16. Agent View

Shows interactions handled by one agent.

Table:

| Time  | Account | Task       | Tokens |
| ----- | ------- | ---------- | ------ |
| 10:30 | user-a  | Debug code | 2200   |

---

# 17. Agent Performance Metrics

For each agent:

```text
Coding Agent

Requests:
12000

Average Tokens:
2200

Average Latency:
3.8s

Quality Score:
4.5/5

Routing Accuracy:
94%
```

---

# 18. Message View

Shows a single interaction.

Header:

```text
Account:

wechat:user123


Agents:

orchestrator
research
coding


Tokens:

8200


Latency:

7.4s
```

---

# 19. Execution Trace Viewer

Display timeline:

```text
10:00:01

Orchestrator

Selected:
Research + Coding


10:00:03

Research Agent

Tool:
Search


10:00:07

Coding Agent

Generated:
Migration Code


10:00:10

Final Response
```

---

# 20. Trace Table Configuration

Because providers expose different fields:

The UI should:

1. inspect available fields;
2. dynamically generate columns;
3. allow column selection;
4. save user preferences.

---

# 21. Quality Evaluation Framework

Quality evaluation is separate from observability.

Supported evaluators:

* LLM Auto Rater;
* Perplexity diagnostics.

---

# 22. LLM Auto Rater

Purpose:

Evaluate response quality.

The evaluation should not run automatically.

User clicks:

```text
Evaluate Response
```

Flow:

```text
Interaction

    |

Question + Answer

    |

LLM Judge

    |

Store Evaluation

    |

Display Scores
```

Prompt:

```text
You are evaluating an AI assistant response.

Score from 1-5:

1. Correctness
2. Relevance
3. Completeness
4. Clarity

Question:

{question}

Assistant Answer:

{answer}

Return JSON only.
```

Example:

```json
{
  "correctness":5,
  "relevance":4,
  "completeness":4,
  "clarity":5,
  "overall":4.5
}
```

---

# 23. Evaluation Storage

Store:

```yaml
evaluation_id:

interaction_id:

evaluator_model:

prompt_version:


scores:

  correctness:

  relevance:

  completeness:

  clarity:


timestamp:
```

---

# 24. Perplexity Distribution Analysis

Perplexity is a diagnostic metric.

It should not be interpreted as a direct quality score.

The purpose is:

> Show where this response's perplexity falls compared with historical responses.

---

## Distribution Visualization

For each response:

Display:

* histogram/density distribution;
* median;
* percentile markers;
* current response marker.

Example:

```text
Response Perplexity Distribution


Frequency


       *
     * * *
   * * * * *
 * * * * * * *


-----------------------------

                 |
                 |
          Current Response

          Perplexity: 82

          Percentile: 93%
```

---

# 25. Perplexity Baselines

Compute distributions:

## Global

All responses:

```text
All accounts
All agents
Last 7 days
```

---

## Account

Same user:

```text
Same account
Last 7 days
```

---

## Specialist Agents

Agents involved:

```text
Exclude orchestrator

Include:

Coding
Research
Other specialists
```

---

## Orchestrator

Responses generated by:

```text
Main/orchestrator agent
```

---

# 26. Multi-Agent Metrics

## Routing Accuracy

Measure:

Did the orchestrator select the correct agent?

Formula:

```text
correct routes / total routes
```

---

## Delegation Efficiency

Measure unnecessary agent calls.

Example:

```text
Simple question

Orchestrator

  |
  + Coding

  + Research
```

Metric:

```text
Useful agent calls / total calls
```

---

## Collaboration Quality

Measure:

* whether agents complemented each other;
* whether aggregation improved results;
* whether contradictions were resolved.

---

# 27. Privacy and Security

The dashboard exposes:

* user messages;
* responses;
* traces;
* tool outputs.

Requirements:

* local-only default;
* authentication support;
* configurable redaction.

Example:

```text
[x] Emails

[x] Phone numbers

[x] API keys
```

---

# 28. Backend API

Frontend communicates through APIs.

Examples:

```text
GET /api/dashboard/summary

GET /api/accounts

GET /api/accounts/{id}/messages

GET /api/agents

GET /api/messages/{id}

GET /api/messages/{id}/trace

POST /api/messages/{id}/evaluate
```

---

# 29. Implementation Roadmap

## Phase 1

Build:

* collector;
* database;
* dashboard;
* account view;
* agent view;
* trace viewer.

---

## Phase 2

Add:

* LLM evaluator;
* evaluation storage;
* quality dashboards.

---

## Phase 3

Add:

* routing analytics;
* agent regression detection;
* prompt comparison;
* agent evolution tracking.

---

# 30. Success Criteria

The dashboard succeeds when operators can answer:

## Operations

* Who uses the system?
* Which agents consume resources?

## Debugging

* Why did this answer happen?

## Quality

* Was the response good?
* Was routing correct?

## Improvement

* Did agent changes improve outcomes?

---

# Final Architecture

```text
                OpenClaw Runtime

                       |

                       v

              Trace Collection

                       |

                       v

             Analytics Database

                       |

                       v

             Observability UI

                       |

                       v

          Evaluation + Improvement Loop
```

The goal is to make OpenClaw multi-agent systems observable, measurable, and continuously improvable.
