# Remote Kubernetes Work Rules Design

## Objective

Add repository-level operating rules for releasing Jarvis without committing
Kubernetes manifests or secrets to Git.

## Scope

- Create a root-level `AGENTS.md` containing deployment and release rules.
- Do not modify `.github/workflows/docker.yml` or
  `.github/workflows/update_pod.yml`.
- Keep `jarvis.yaml` ignored by Git.
- Do not change application code, Kubernetes manifests, or the remote server as
  part of adding the rules.

## Repository and Image Workflow

1. After an agent changes code, it must run the checks relevant to those
   changes.
2. It must commit and push only the files belonging to the current task to
   GitHub. Existing unrelated staged or unstaged changes must remain untouched.
3. A push to `master` triggers the existing GitHub Actions image build.
4. The agent must monitor the triggered GitHub Actions run until it succeeds or
   reaches a terminal failure, and report failures with the relevant job or
   step.
5. Images are supplied by the
   `registry.cn-hangzhou.aliyuncs.com/lexmargin/jarvis` repository. The image
   tag is the version produced by the existing GitHub Actions workflow
   (currently `latest`). Agents must not build or push release images locally.

## Remote Deployment Boundary

- The service runs on `1.15.231.125` under the `root` account.
- Remote project files live under `/root/jarvis`.
- Kubernetes is the only supported service deployment mechanism.
- Kubernetes YAML files remain local and untracked. When a manifest changes,
  the agent may securely synchronize only that manifest to `/root/jarvis`.
- Synchronizing a manifest does not authorize `kubectl apply`, Pod deletion,
  service restarts, or other remote mutations unless the user explicitly
  requests them.
- Agents must not manually pull an image unless the user explicitly asks,
  because the established deployment pipeline supplies the image.

## Secret Handling

- Never place passwords, API keys, kubeconfig contents, tokens, or other
  credentials in `AGENTS.md`, Kubernetes YAML committed to Git, source files,
  shell history, logs, or assistant responses.
- Remote authentication must come from an SSH key, environment variable, or
  another local secure credential mechanism.
- Commands and status reports must avoid echoing or otherwise exposing
  credentials.

## Acceptance Criteria

- A root-level `AGENTS.md` records the workflow above without containing any
  secret value.
- Existing GitHub Actions files remain unchanged.
- `jarvis.yaml` remains ignored.
- No Kubernetes YAML is added to Git.
- The rules explicitly protect unrelated working-tree changes and require
  monitoring GitHub Actions after code pushes.
