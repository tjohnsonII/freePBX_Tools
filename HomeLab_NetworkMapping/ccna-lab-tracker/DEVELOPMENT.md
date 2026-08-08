# Development Workflow — GitHub + VS Code

How to work on this app locally.

## 1. Get the repo open in VS Code

If you don't have the repo locally yet:

```bash
git clone https://github.com/tjohnsonII/freePBX_Tools.git
code freePBX_Tools
```

Install the **GitHub Pull Requests and Issues** extension — lets you view/create PRs,
review diffs, and see issues without leaving the editor.

## 2. Run the app locally while you edit

```bash
cd HomeLab_NetworkMapping/ccna-lab-tracker
npm install
npm run dev
```

Opens at `localhost:3011`. Leave this running in VS Code's integrated terminal —
changes to the code hot-reload in the browser.

## 3. Edit → commit → push loop

- Make your code changes
- VS Code's **Source Control** panel (left sidebar, branch icon) shows every changed
  file as a diff — click a file to see exactly what changed before staging it
- Stage files (+ icon), write a commit message, hit the checkmark to commit
- Click **Sync Changes** (or `git push`) to push to GitHub

## 4. Branches, if you want to keep `main` stable

- Bottom-left corner of VS Code shows your current branch — click it → "Create new
  branch" before starting a feature
- Push that branch, then use the GitHub extension (or github.com) to open a PR into
  `main`
- For a solo project, committing straight to `main` is fine too — branches matter
  more once something else depends on this repo not breaking

## Note on the Grafana GitHub App

The GitHub App `timsablab-grafana-sync` (used for automated Grafana dashboard sync,
see `HomeLab_NetworkMapping/grafana-provisioning/README.md`) is scoped narrowly for
that purpose and unrelated to normal development here. Personal commits just use
your own GitHub account — VS Code prompts you to sign in via browser on first
push/pull.
