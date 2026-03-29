<!-- ──────────────────────────────────────────────────────────────────────────
     BUG REPORT
     Use this template for broken or incorrect behaviour.
     For new capabilities → use feature-request. For chores → use task.
     ────────────────────────────────────────────────────────────────────────── -->

## 📝 Summary

<!-- One sentence: what broke, in which component, under what condition.
     Example: "dateparser returns None for German input 'morgen um 14 Uhr'
     and the Ollama fallback times out after 30s." -->

## 🖥️ Environment

| Field | Value |
|---|---|
| Horae version / commit | <!-- `git rev-parse --short HEAD` --> |
| Python version | <!-- `python --version` --> |
| OS | <!-- e.g. Ubuntu 24.04, macOS 15, Android 15 --> |
| Ollama model | <!-- e.g. mistral:7b-instruct-q4_K_M --> |
| Affected component | <!-- NLP / LLM / CalDAV / API / Tasker --> |

## 🔁 Steps to Reproduce

<!-- Numbered, specific steps. Include the exact command or HTTP request. -->

1. 
2. 
3. 

## 😭 Actual Behavior

<!-- What did Horae actually do? Paste the full error output (stack trace, log
     lines, HTTP response) inside a code block if applicable. -->

```
paste error / unexpected output here
```

## 😂 Expected Behavior

<!-- What should have happened instead? -->

## 🎯 Acceptance Criteria

```gherkin
Feature: <the behaviour that was broken>

  Scenario: <normal case that should work again>
    Given <precondition that previously triggered the bug>
    And <additional setup if needed>
    When <action that caused the error>
    Then <correct outcome>
    And <additional assertion if needed>

  Scenario: <regression guard — ensure the original trigger no longer breaks>
    Given <the exact environment from "Steps to Reproduce">
    And <relevant config or state>
    When <same action>
    Then <no error, correct output>
    And <original data remains intact>
```

## 🧪 Test Planning

- **Unit / Integration tests:** <!-- Which test files need new cases? Which fixtures/mocks? -->
- **E2E test needed?** <!-- Yes / No — if yes, describe the scenario briefly -->
- **Components to verify after fix:** <!-- e.g. NLP parsing, CalDAV creation, API response -->

## 📦 Affected Component(s)

- [ ] NLP parsing (dateparser / heuristic)
- [ ] LLM parsing (Ollama fallback)
- [ ] CalDAV client (caldav / Radicale integration)
- [ ] API (FastAPI endpoints)
- [ ] Android integration (Tasker / HTTP)
- [ ] Core / config
- [ ] Docker / deployment

## 🗄️ Relevant Logs

<!-- Stack traces, screenshots, log output — paste inside code blocks.
     Delete this section if empty. -->

## 🔗 References

<!-- Related issues, external docs, upstream bug trackers.
     Delete this section if empty. -->

---

/label ~bug ~"needs-triage"
