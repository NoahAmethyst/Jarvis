# Jarvis Repository Work Rules

## Release workflow

- After changing application code, run the checks relevant to the changed files.
- Commit and push only files that belong to the current task. Preserve unrelated staged, unstaged, and untracked work.
- Push completed code changes to GitHub on `master` so the existing GitHub Actions workflow builds and publishes the image.
- After each code push, monitor the triggered GitHub Actions run until it succeeds or reaches a terminal failure. If it fails, report the failing job and step before making further deployment changes.
- Release images come from `registry.cn-hangzhou.aliyuncs.com/lexmargin/jarvis`. Use the tag produced by the existing workflow, currently `latest`.
- Do not build or push release images locally.

## Remote Kubernetes deployment

- The service runs on `1.15.231.125` using the `root` account.
- The remote working directory is `/root/jarvis`.
- Deploy and run the service only through Kubernetes.
- Sanitized `jarvis.yaml` and `llm.yaml` files containing only empty values, placeholders, or environment-variable references may be committed.
- Never put a real password, API key, token, kubeconfig value, or other credential in a tracked YAML file or Git commit.
- Put secret-bearing local configuration in an ignored `*.local.yaml` or `*.secret.yaml` file.
- Before staging a YAML change, inspect the staged diff and scan the commits that will be pushed for secrets without printing secret values.
- When a Kubernetes manifest changes, securely synchronize only the intended manifest to `/root/jarvis`. A secret-bearing local manifest may be copied to the required remote filename but must remain untracked locally.
- Synchronizing a manifest does not authorize `kubectl apply`, Pod deletion, service restart, or another remote mutation. Perform those actions only when the user explicitly requests them.
- Do not manually pull an image on the remote server unless the user explicitly requests it.

## Credentials and secrets

- Never store passwords, API keys, tokens, kubeconfig contents, or other credentials in this repository, Kubernetes YAML committed to Git, shell history, logs, or assistant responses.
- Obtain remote authentication from an SSH key, environment variable, or another local secure credential mechanism.
- Never echo credentials in commands or status output.
