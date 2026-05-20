# Kargo Promotion Inflation & Architecture Review

This document outlines the root causes of the `Promotion` creation bugs we encountered, an analysis of Kargo's internal validation mechanisms, and proposed architectural changes to make the Kargo MCP Server robust against these Kargo API quirks.

## Executive Summary

The MCP Server is now successfully authenticating, bypassing API bugs, triggering promotions, and correctly passing Git credentials to Kargo pipelines. However, we uncovered a critical limitation in how Kargo handles `PromotionTask` inflation when using direct Kubernetes CRD creation (`/v1beta1/resources`). 

## Key Observations

1. **The API Server RPC Bug**: 
   - The official Kargo REST RPC endpoint (`POST /v1beta1/projects/{project}/stages/{stage}/promotions`) accepts payloads and returns a `200 OK` empty response, but **fails to actually create the Promotion CRD** in the cluster. This is likely due to an upstream bug in Kargo's v1beta1 proxy mapping.
   
2. **The `/v1beta1/resources` Workaround**: 
   - To bypass the RPC bug, we successfully routed `create_promotion` through the generic `/v1beta1/resources` endpoint to create the `Promotion` CRD directly. 

3. **The Webhook "Inflation" Rejection**:
   - Kargo's Admission Webhook mandates that a `Promotion` CRD must have a fully populated `steps` array at creation time.
   - When using the high-level Kargo CLI, the CLI or API Server automatically **inflates** (merges) the `PromotionTask` steps into the `Promotion` object.
   - Because our MCP Server creates the CRD directly, this inflation is skipped. If a Stage references a task (`task: name: promote`), the webhook receives uninflated steps and throws: `Stage "dev" defines no promotion steps`.
   - *Proof:* When we manually patched the Stage to use **inline steps** (e.g. `uses: git-clone`), the MCP Server successfully created the Promotion, and the pipeline executed perfectly!

## Proposed Approaches to Make the MCP Server Robust

To solve the inflation issue without relying on the buggy Kargo RPC endpoint, we have two viable architectural paths:

### Approach 1: Implement Client-Side Inflation in the MCP Server (Recommended)
We can update the `create_promotion` method in `kargo_service.py` to act as an intelligent Kargo client. Before generating the `Promotion` CRD, the MCP Server will:
1. Fetch the target `Stage`.
2. Inspect `stage.spec.promotionTemplate.spec.steps`.
3. If it detects a `PromotionTask` reference (`task: {name: ...}`), it will dynamically call `get_promotion_task()` via the Kargo API.
4. Extract the `steps` from the `PromotionTask`, perform any necessary variable merging, and inject the raw, inflated steps into the `Promotion` payload.
5. Submit the fully inflated CRD to `/v1beta1/resources`.

**Pros:** 
- Makes the MCP Server incredibly robust and autonomous.
- Fully supports advanced Kargo features like `PromotionTask` without failing.

### Approach 2: Enforce "Inline-Only" Pipeline Definitions
Update the MCP Server documentation and Prompts to mandate that Kargo pipelines managed by AI agents must use **inline steps** directly within the `Stage` definition, explicitly disallowing `PromotionTask` references.

**Pros:** Zero additional code complexity in `kargo_service.py`.
**Cons:** Limits the user from using standard Kargo DRY (Don't Repeat Yourself) pipeline abstractions.

---

> [!IMPORTANT]
> Please review the two approaches above. 
> 
> Approach 1 requires a small refactor of `kargo_service.py` to add intelligent template inflation, but will yield a production-grade, bulletproof MCP Server that natively understands Kargo's advanced `PromotionTask` logic.
>
> Let me know if you approve moving forward with **Approach 1**!
