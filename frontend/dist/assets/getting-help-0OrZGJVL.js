const e=`# Getting help & reporting problems\r
\r
Stuck, found a bug, or missing a feature? Two doors, both watched:\r
\r
- **Discord** — [discord.gg/j6hnJBFtXE](https://discord.gg/j6hnJBFtXE) — ask in\r
  **#help**; usually the fastest way to get unstuck. Feature ideas and votes\r
  live in **#roadmap**.\r
- **GitHub** — [Issues](https://github.com/Fr3sher/FLT/issues) —\r
  best for reproducible bugs and feature requests; the templates walk you\r
  through what to include.\r
\r
---\r
\r
## What makes a report solvable\r
\r
The difference between a five-minute fix and a week of guessing is almost\r
always the same four things:\r
\r
1. **Version** — shown in Settings → Maintenance → Updates ("Current build").\r
2. **Environment** — OS, and whether you run API-only, full local, or Docker.\r
3. **What you did → what you expected → what happened** — three short lines\r
   beat three paragraphs.\r
4. **The log** — the last lines of the server log usually name the real error.\r
   Settings → Maintenance → 🪵 Server log → **Copy all**.\r
\r
## Or let the app write it for you\r
\r
The **diagnostic report** button below assembles all of that in one click:\r
version, OS, capability status, non-secret settings and the last log lines —\r
formatted, copied to your clipboard, ready to paste into Discord or a GitHub\r
issue.\r
\r
What it deliberately **never** includes: your API keys or tokens (only\r
whether each one is set) and your folder paths (only whether each one is\r
configured). One caveat: the log tail can mention file names from your machine\r
— skim the paste before posting if that matters to you.\r
\r
## Feature requests\r
\r
Describe the **job you were doing when you missed the feature** — the problem\r
is more valuable than the proposed solution. Post it in Discord **#feature-requests** or\r
open a GitHub issue with the *Feature request* template.\r
\r
## Support the project\r
\r
FLT - Fresh LoRa Trainer is free and source available under the\r
[PolyForm Noncommercial license](../../LICENSE). You can support upstream\r
LoRA Dataset Studio development, API testing and test GPUs through\r
**monthly support** on [Patreon](https://www.patreon.com/c/Loraperfectgf)\r
or [GitHub Sponsors](https://github.com/sponsors/perfectgf).\r
\r
The small support message on the datasets page can be dismissed. These links\r
remain available through **Help & guide → Support LDS**.\r
The best free ways to help are just as welcome: report bugs, share ideas on\r
Discord, and star the repo.\r
`;export{e as default};
