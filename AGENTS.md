# Project workflow

## Linear status and completion

- Keep an active parent issue In Progress when work on its required children has started.
- Mark a parent Done only after all required subtasks are complete and the parent's acceptance criteria are verified. Check current child statuses before closing it.
- Keep partially implemented original issues open. A completed delivery slice does not complete overlapping requirements in the original issues.
- Before advancing work, review unfinished acceptance criteria and make remaining work and explicit deferrals visible. Never skip work because a related slice is Done.
- Record verification evidence and outstanding requirements on the relevant issue. Do not check off unverified acceptance criteria.
- Keep issues requiring live provider or environment validation open until that validation passes; distinguish mocked tests from live checks.
- Prefer updating existing issues to creating overlapping progress-report issues. Create a new issue when it represents distinct scope missing from the backlog.
- Linear views may display an open parent as context for a completed child. Use the issue's actual status and child progress, not its visual position in a grouped view, to judge completion.
