# Kargo Built-in Promotion Steps

Kargo provides a rich set of built-in promotion steps that can be composed into promotion templates.

## Git Operations

| Step | Description |
|------|-------------|
| `git-clone` | Clone a Git repository for modification |
| `git-push` | Push changes back to a Git repository |
| `git-open-pr` | Open a pull request with promotion changes |
| `git-wait-for-pr` | Wait for a PR to be merged |
| `git-commit` | Commit changes to the working tree |
| `git-clear` | Clear the working tree |

## Helm Operations

| Step | Description |
|------|-------------|
| `helm-update-chart` | Update chart dependency versions in Chart.yaml |
| `helm-update-image` | Update image tags in Helm values |
| `helm-template` | Render Helm templates |

## ArgoCD Operations

| Step | Description |
|------|-------------|
| `argocd-update` | Update an ArgoCD Application source and sync |

## YAML/JSON Operations

| Step | Description |
|------|-------------|
| `yaml-update` | Update fields in YAML files |
| `json-update` | Update fields in JSON files |
| `kustomize-set-image` | Update image in kustomization.yaml |
| `kustomize-build` | Build kustomize overlay |

## CI/CD Integrations

| Step | Description |
|------|-------------|
| `gha-run` | Trigger a GitHub Actions workflow |
| `gha-wait` | Wait for a GitHub Actions workflow to complete |

## Infrastructure

| Step | Description |
|------|-------------|
| `hcl-update` | Update HCL (Terraform) files |
| `tf-apply` | Apply Terraform changes |

## General

| Step | Description |
|------|-------------|
| `http` | Make HTTP requests (webhooks, notifications) |
| `copy` | Copy files within the working directory |
| `jira-create` | Create a Jira issue |
| `jira-transition` | Transition a Jira issue |
| `custom` | Run a custom container as a promotion step |

## Composing Steps

Steps are composed in a `PromotionTask` or inline in a Stage spec:

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: PromotionTask
metadata:
  name: deploy-via-argocd
spec:
  steps:
    - uses: git-clone
      config:
        repoURL: ${{ vars.gitRepoURL }}
    - uses: helm-update-image
      config:
        images:
          - image: ${{ imageFrom(freight, vars.imageRepo).tag }}
    - uses: git-push
    - uses: argocd-update
      config:
        apps:
          - name: ${{ vars.appName }}
```
