# Argo CD Integration Reference

## Table of Contents
1. [Application Authorization Annotation](#application-authorization-annotation)
2. [Using `argocd-update` in Promotion Steps](#using-argocd-update-in-promotion-steps)
3. [Stage Health Checks via Argo CD](#stage-health-checks-via-argo-cd)

## Application Authorization Annotation

Before a Kargo Stage can mutate or sync an Argo CD `Application`, the Argo CD `Application` resource must include the authorization annotation:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: guestbook-dev
  namespace: argocd
  annotations:
    kargo.akuity.io/authorized-stage: "<project>:<stage>"
```

If this annotation is missing or points to a different `<project>:<stage>`, the `argocd-update` step fails with an authorization error (flagged as `ARGOCD_SYNC_OR_AUTH_FAILED` by `kargo_diagnose_stage`).

## Using `argocd-update` in Promotion Steps

After `git-push` updates the stage branch (or after `git-wait-for-pr` merges a PR), add `argocd-update` so Kargo refreshes and syncs the Argo CD `Application` to the exact Git commit:

```yaml
- uses: argocd-update
  config:
    apps:
      - name: guestbook-${{ ctx.stage }}
        namespace: argocd
        sources:
          - repoURL: ${{ vars.gitopsRepo }}
            desiredRevision: ${{ outputs.commit.commit }}
```

## Stage Health Checks via Argo CD

When a Stage's most recent Promotion includes an `argocd-update` step, Kargo automatically monitors the referenced Argo CD Applications and populates `Stage.status.health` (`Healthy`, `Progressing`, `Degraded`, or `Unknown`). Read `kargo://projects/{project}/stages/{stage}` or run `kargo_diagnose_stage` to inspect live Argo CD application health.
