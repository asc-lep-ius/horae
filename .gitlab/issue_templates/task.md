<!-- ──────────────────────────────────────────────────────────────────────────
     TASK
     Use this template for refactors, chores, research spikes, dependency
     updates, documentation, and CI/tooling work — anything not user-facing.
     For new behaviour → feature-request. For broken behaviour → bug-report.
     ────────────────────────────────────────────────────────────────────────── -->

## 📋 Summary

<!-- What needs to be done and why? One short paragraph.
     Focus on the goal, not the implementation. -->

## 🎯 Motivation / Context

<!-- Why does this matter now? Link to the broader feature, issue, or
     architectural decision this unblocks.
     Examples: "Prerequisite for #42.", "Technical debt causing test flakiness." -->

## ✅ Definition of Done

<!-- GitLab renders these as interactive checkboxes — tick them off as you go.
     Be specific enough that any contributor can self-assess whether they're done. -->

- [ ] <!-- e.g. Existing tests still pass (`uv run pytest`) -->
- [ ] <!-- e.g. Ruff reports zero errors (`uv run ruff check .`) -->
- [ ] <!-- e.g. Relevant docs / docstrings updated -->

## 🧪 Verification

<!-- Which commands / tests confirm this task is complete? -->

```bash
# e.g.
uv run pytest tests/
uv run ruff check .
```

## 🚫 Out of Scope

<!-- What does this issue explicitly NOT touch?
     Prevents contributors from over-engineering or gold-plating. -->

- 

## 🔗 Dependencies

<!-- Is this blocked by another issue? Does completing this unblock something? -->

| Relationship | Issue |
|---|---|
| Blocked by | <!-- #N or n/a --> |
| Unblocks | <!-- #N or n/a --> |

## 📦 Affected Component(s)

- [ ] NLP parsing (dateparser / heuristic)
- [ ] LLM parsing (Ollama fallback)
- [ ] CalDAV client (caldav / Radicale integration)
- [ ] API (FastAPI endpoints)
- [ ] Android integration (Tasker / HTTP)
- [ ] Core / config
- [ ] Docker / deployment
- [ ] Docs / README
- [ ] CI / tooling

---

/label ~task ~"needs-triage"
