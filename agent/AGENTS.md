# Scoring-Optimized Solver Instructions

Your output is scored by **positional line-level exact matching** against a reference solution.

```
score = matched_lines / max(your_changed_lines, reference_changed_lines)
```

Each added or removed line is extracted from the diff in top-to-bottom file order (files sorted alphabetically), then compared **position-by-position**. A line scores only if it matches the reference line at the **same position**. Any insertion, deletion, or reordering before a correct line shifts all later positions and kills their score.

This means:
- **Correct file selection** is mandatory — touching a wrong file adds unmatched lines.
- **Correct location within a file** is mandatory — a correct change at the wrong position scores zero.
- **Extra lines anywhere** dilute the score (max denominator grows).
- **Missing lines anywhere** reduce matched numerator.

---

## Workflow

1. **Identify target symbols.** Read the task. Extract the specific class names, function names, variable names, feature names, and file paths mentioned. Do NOT start editing yet.
2. **Search first, always.** Run `grep -rn "SymbolName\|feature_name"` to find the exact files and line numbers. Do this for every symbol mentioned before opening any file. This reveals whether a file already exists, where it lives, and what partial implementation is already there.
3. **Determine: existing file or new file?** If grep finds a matching file, that file is the target — read it in full before editing. If grep finds nothing, look for the most similar existing implementation as a structural template.
4. **Read each target file in full.** Read every file you will edit from start to finish. Note: indentation style (tabs/spaces/width), quote style, semicolons, trailing commas, line endings, surrounding code patterns.
5. **Plan the minimal change.** Decide the exact lines to add/remove. The reference is a real developer commit — it will be surgical. Match that precision.
6. **Check for companion files.** If you are touching a source file that has a corresponding localization, registration, or config file, check whether those companion files also need updating. Common companions:
   - `lang/en_us.json` → also update `lang/ja_jp.json` (and any other language files in the same directory)
   - New spell/item/block class → grep for the registration file (e.g., `SpellRegistry`, `ItemRegistry`) and add the registration entry
7. **Edit from top to bottom, alphabetically.** Process files in alphabetical path order. Within each file, make all edits in a single top-to-bottom pass.
8. **Stop.** Do not summarize, explain, verify, test, or re-read.

---

## Rules

### Mandatory

- **Minimal diff.** Change only exactly what the task requires. Every extra changed line hurts your score. Do not touch formatting, imports, comments, type annotations, blank lines, or anything the task does not explicitly ask for.
- **Exact style match.** Mirror the surrounding code character-for-character: indentation (tabs vs spaces, and exact width), quote style, semicolons, trailing commas, spacing around operators, brace placement. Read the file first and copy existing patterns.
- **No cosmetic changes.** Never reformat, reorder imports, rename variables, fix unrelated bugs, add error handling, add logging, or modify whitespace outside the changed region.
- **Alphabetical file order.** When editing multiple files, process them in lexicographic path order. This matches how the scoring system orders changed lines from multiple files.
- **Top-to-bottom within a file.** Within each file, make all edits in a single top-to-bottom pass. Never make an earlier edit after a later one — that would reorder your diff lines relative to the reference.
- **Direct implementation only.** Use the simplest approach that matches the task. Follow patterns already present in the codebase. Do not introduce abstractions, helpers, or generalization beyond what is explicitly requested.
- **No commits, no tests, no builds.** The evaluation framework captures your diff automatically. Do not run any verification.
- **No re-reads after editing.** Do not read a file again after you have edited it.

### File Creation vs Modification

- **Always grep first.** Before deciding to create a new file, use `grep -rn "ClassName\|file_name"` to check if it already exists as a partial or stub implementation. Tasks frequently say "implement X" when X already has a skeleton — in that case, modify the existing file rather than creating a new one.
- **New files only when truly absent.** Create a new file only when grep confirms the file does not exist. When creating, find the most similar existing file as a structural template and mirror its package declaration, imports, class structure, and formatting.
- **Registration and localization are almost always required** when adding a new class (spell, item, block, entity). After implementing the class, grep for the registration file (e.g., `SpellRegistry`, `ModSpells`, `ItemRegistry`) and add the new entry mirroring how existing entries are registered.

### Locating Changes

- **grep before read.** Use `grep -rn "functionName\|ClassName\|variable"` to identify which files and which line numbers are relevant before you open anything.
- **Read the full file** of every file you will edit, not just the surrounding function. This lets you see duplicate symbols, understand imports, and anchor your edits precisely.
- **One file = one read.** Read each target file exactly once, before any edit to it.

### Localization Files

- **Dual-language rule.** When adding or modifying localization keys in any language file (e.g., `en_us.json`), check the directory for other language files (e.g., `ja_jp.json`) and add the equivalent keys in each one.
- **Insertion position.** Localization keys in JSON lang files are typically grouped by feature prefix (e.g., `"spell.apprenticecodex.tamers_pocket"`, `"ui.apprenticecodex.tamers_pocket.*"`). Insert new keys immediately after the last existing key with the same prefix, to match the alphabetical ordering of the reference diff.
- **Key naming pattern.** Follow the exact same key prefix convention already used for the feature (e.g., `ui.apprenticecodex.tamers_pocket.current_count` → `ui.apprenticecodex.tamers_pocket.deploy_count` uses the same namespace).

### When Uncertain

- **Smaller is always better.** A correct 5-line patch beats an incorrect 10-line patch. If you are unsure whether a secondary change is required, leave it out.
- **Do not guess file paths.** If a file is not mentioned in the task and grep does not surface it, do not touch it.
- **Do not infer undescribed behavior.** Implement only what the task explicitly describes. If the task says "add a validate function", add exactly that — no tests, no exports unless they are in the same edit region of an existing file the task points to.

---

## Common Patterns

### Implementing a new spell / class / feature

1. **Grep first**: `grep -rn "FeatureName\|feature_name"` — check if an existing file with that class already exists.
2. If found: read the file in full; add only the missing methods, fields, or logic described by the task.
3. If not found: `grep -rn "extends AbstractSpell\|class.*Spell"` (or equivalent) to find the most similar existing implementation. Read it fully. Create the new file mirroring its structure. Keep it minimal — only implement what the task acceptance criteria explicitly require.
4. After the implementation, grep for the registry file and add the registration entry.
5. Add localization keys to ALL language files in the lang directory.

### Adding a new function or method
- Read the file in full first.
- Insert the function at the same location the reference would: typically grouped with related functions (same class block, same section, alphabetically if the file is sorted).
- Match exactly: blank lines before/after, decorator patterns, access modifiers, docstring style (or lack of one).

### Modifying an existing function
- Read the full function (not just the surrounding lines) to understand its current logic.
- Make the smallest possible change: often a single line insertion or replacement.
- Do not touch any lines outside what the task specifies.

### Adding an import
- Add it in the same import group (stdlib/third-party/local) where the reference would.
- Match the existing import style exactly (named vs default, aliased, indentation).
- If unsure of group placement: insert at the end of the existing imports for that package type.

### Changing a config value or constant
- Edit only the value, not surrounding whitespace or comments.

---

## Anti-patterns (never do these)

- Running tests or builds to verify
- Adding `# type: ignore` or suppressing linter warnings
- Wrapping new code in try/except or error guards not in the task
- Adding TODO comments
- Changing variable names from what the task specifies
- Touching `__init__.py`, `index.ts`, or barrel files unless the task explicitly references them
- Reformatting a block you are editing "while you're there"
- Adding blank lines before or after your change unless they match the reference pattern
- Creating a new file when an existing partial implementation already exists in the repo
- Updating only `en_us.json` while ignoring other language files in the same directory
- Assuming the task description covers ALL files that need changing — grep to discover companion files (registration, localization, tests) that are implicitly required
