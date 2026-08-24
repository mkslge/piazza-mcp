---
name: comment-skill
description: Add or improve code documentation with a brief explanation for every named function and focused comments around non-obvious logic. Use when the user asks to document code, add comments or docstrings, explain functions in source files, or make an implementation easier for future maintainers to understand.
---

# Comment Skill

Document code without changing its behavior. Prefer concise explanations that
capture intent, assumptions, and constraints instead of translating syntax into
English.

## Workflow

1. Read the requested files and the repository's documentation conventions.
2. Identify every named function and method in scope, including private,
   asynchronous, nested, and protocol or abstract functions.
3. Add a brief explanation at the start of each function:
   - Use the language's native documentation form.
   - In Python, make a short docstring the first statement in the function.
   - In languages with declaration comments, place the documentation directly
     above the declaration.
   - State what the function accomplishes in its surrounding domain.
   - Document parameters, return values, exceptions, or side effects only when
     they are not obvious or when the repository's established style requires
     them.
4. Add inline comments immediately before confusing logic. Explain why the
   logic exists, which invariant it preserves, or why a less obvious approach
   is necessary.
5. Review the diff and remove comments that repeat names, operators, control
   flow, or other self-evident behavior.
6. Run the repository's relevant checks to verify that documentation-only edits
   did not alter behavior or break formatting.

## Commenting Rules

- Document every named function in the user-requested scope.
- Keep routine function documentation to one concise sentence when possible.
- Preserve useful existing documentation and improve it instead of duplicating
  it.
- Place explanations next to the code they clarify; do not collect detached
  comments at the end of a function.
- Comment complex validation, boundary calculations, state transitions,
  compatibility workarounds, and security constraints when their rationale is
  not evident from the code.
- Do not comment straightforward assignments, simple delegation, standard loop
  mechanics, or syntax already made clear by good names.
- Do not modify behavior, rename symbols, refactor code, or reformat unrelated
  lines as part of a documentation request.
- Do not add docstrings to lambdas because they are not named function
  declarations; explain unusual surrounding logic instead when needed.

## Quality Check

Before finishing, confirm that every named function in scope has introductory
documentation, every inline comment explains non-obvious intent, and the diff
contains documentation-only changes unless the user requested more.
