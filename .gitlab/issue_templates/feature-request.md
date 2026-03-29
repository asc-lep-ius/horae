<!-- ──────────────────────────────────────────────────────────────────────────
     FEATURE REQUEST
     Use this template for new capabilities, enhancements, or user-facing changes.
     For broken behaviour → use bug-report. For chores/refactors → use task.
     ────────────────────────────────────────────────────────────────────────── -->

## 🎉 Problem Statement

<!-- What pain point does this solve? Who experiences it?
     Example: "When parsing German natural-language input like 'Zahnarzt
     übermorgen am Nachmittag', dateparser mis-identifies the date
     and Ollama fallback is not triggered." -->

## 💁 User Story

> As a **[persona]**, I want to **[action]**, so that **[benefit]**.

<!-- Personas: user (creating events via phone/desktop), developer (maintaining Horae) -->

## 💡 Proposed Solution

<!-- Your candidate approach — not the only valid one, just a starting point.
     Keep it short. The Acceptance Criteria below is what actually matters. -->

## 🎯 Acceptance Criteria

```gherkin
Feature: <feature name>

  Scenario: <happy path>
    Given <precondition>
    And <additional precondition if needed>
    When <action taken>
    Then <expected outcome>
    And <additional assertion if needed>

  Scenario: <edge case or failure path>
    Given <precondition>
    When <action taken>
    Then <expected outcome>
```

## 🧪 Test Planning

- **Unit tests:** <!-- Which test files need new cases? Which fixtures/mocks? -->
- **Integration tests:** <!-- Which layers/systems involved? -->
- **E2E test needed?** <!-- Yes / No — if yes, describe the scenario briefly -->

## 🚫 Out of Scope

<!-- Explicitly list what this issue does NOT cover.
     This prevents well-meaning contributors from expanding scope. -->

- 

## 📦 Affected Component(s)

- [ ] NLP parsing (dateparser / heuristic)
- [ ] LLM parsing (Ollama fallback)
- [ ] CalDAV client (caldav / Radicale integration)
- [ ] API (FastAPI endpoints)
- [ ] Android integration (Tasker / HTTP)
- [ ] Core / config
- [ ] Docker / deployment
- [ ] Docs

## 🤓 Implementation Steps

<!-- Reserved for developers. Add numbered steps with estimates. -->

1. <!-- Step description — (estimate) -->

## ✅ Definition of Ready

- [ ] Scope fits a single iteration (not a hidden epic)
- [ ] Acceptance criteria written in Gherkin
- [ ] Edge cases identified
- [ ] No open questions remaining

---

/label ~feature ~"needs-triage"
