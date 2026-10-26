# Project workflow

## Communication and clarification

- Provide a concise completion report describing what was achieved, the relevant changes, verification performed and its results, and any outstanding limitations. This supersedes the code-only response rule; include code or diffs only when useful or requested.
- Proceed autonomously with clear, authorized work and routine implementation choices that follow established project patterns.
- Stop and ask focused clarification questions only when requirements or context are unclear, an architecture decision is needed, or a new third-party dependency or service would be added. Resolve these questions before implementing the affected work; do not write speculative code.

## Task completion and next work

- After finishing each task, review the current task list and backlog, including unfinished acceptance criteria, dependencies, priorities, and actual issue statuses.
- Recommend the next existing task to take, identify it by its title and issue identifier or link when available, and briefly explain why it should come next. Recommend only; do not start it without authorization.
- If the completed task reveals concrete follow-up work missing from the plan, suggest it separately with the evidence and reason it is needed. Do not invent tasks or create backlog items without authorization.
- If no tasks remain, explicitly say so. If the task list or backlog cannot be accessed, report that limitation instead of claiming there are no tasks or inventing a recommendation.

## Linear status and completion

- Keep an active parent issue In Progress when work on its required children has started.
- Mark a parent Done only after all required subtasks are complete and the parent's acceptance criteria are verified. Check current child statuses before closing it.
- Keep partially implemented original issues open. A completed delivery slice does not complete overlapping requirements in the original issues.
- Before advancing work, review unfinished acceptance criteria and make remaining work and explicit deferrals visible. Never skip work because a related slice is Done.
- Record verification evidence and outstanding requirements on the relevant issue. Do not check off unverified acceptance criteria.
- Keep issues requiring live provider or environment validation open until that validation passes; distinguish mocked tests from live checks.
- Prefer updating existing issues to creating overlapping progress-report issues. Create a new issue when it represents distinct scope missing from the backlog.
- Linear views may display an open parent as context for a completed child. Use the issue's actual status and child progress, not its visual position in a grouped view, to judge completion.
