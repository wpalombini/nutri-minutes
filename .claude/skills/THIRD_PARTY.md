# Third-party skills

These skills are copied from their upstream repositories at a pinned commit, so the build agents in `.claude/agents/` work the same way in every session. Update them by copying a newer commit and recording it here.

| Skill | Source | Commit | Licence |
|---|---|---|---|
| `vercel-react-best-practices` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62` | MIT, as declared in the skill's `SKILL.md` and the repository README |
| `vercel-composition-patterns` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/composition-patterns) | `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62` | MIT, as declared in the repository README |
| `web-design-guidelines` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines), with `guidelines.md` from [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) | `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62` and `434b7f91364665f2f733b310ec54809bf8f37937` | MIT; the guidelines' licence is in `web-design-guidelines/LICENSE-guidelines` |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` | Apache 2.0, in `frontend-design/LICENSE.txt` |

## Changes from upstream
- The two Vercel skill folders are renamed to match the `name` in their `SKILL.md` (`vercel-react-best-practices`, `vercel-composition-patterns`).
- `web-design-guidelines/SKILL.md` reads the pinned `guidelines.md` instead of fetching the latest rules from GitHub on every run, so a change upstream can't alter the agents' instructions without a reviewed PR.

## MIT licence (vercel-labs/agent-skills)
The upstream repository declares the MIT licence but does not include a licence file. Its terms are reproduced here for the copied skills.

> Copyright (c) Vercel
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
