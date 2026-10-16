# A41 transport profile consolidation and phone inventory removal

Date: 2026-10-17. Base: A40 6846266.

Vehicle quantity, seats including the driver and confirmed availability now live
in the transport section. Different seat configurations have separate groups;
the total vehicle count is derived from these groups rather than entered twice.
The equipment editor and request snapshot summary no longer list vehicle stock
as general camping equipment. Existing vehicle records retain their quantities,
capacities and confirmation. A transport count without vehicle records creates
an unconfirmed draft with unknown seats, never assumed transport feasibility.
Edits, removal and missing-information links use the same underlying records.
The shared Profile DTO and database layout are unchanged.

Charged phone is removed from the editor, demo draft and current logistics
checklist, including its stock/quantity clarification and eligibility effect.
Historical snapshots are not rewritten. Personal profile changes still require
explicit saving. The sealed v1/v2/v2.1 packages are unchanged. The updated kernel
skips the Charged phone rule; other equipment requirements and capacity checks
remain enforced.

Because logistics behavior changes, current kernel and v2 dataset-rule identities
append `a-profile-essentials-v1` after `a-meal-clarification-v1` (before the trip
evidence suffix). New runtime seeds use that identity. Safety v2's closed paired
identity set and exported schema include this pair; both previous pairs remain
available for historical verification, with no old/current cross pairing.
Frozen v1 replay code, prompt/text policy and model-role feature flags are
unchanged. B should consume the complete updated baseline before integration,
not copy only the UI files or retain a hard-coded previous kernel identity.

Validation:

- 136 affected backend tests passed: logistics rules, audit storage and identity,
  role registration, archived replay, v2 Adapter/HTTP demonstrations and issue
  mapping. The broader suite was started and interrupted in favor of focused
  coverage; no full-suite pass is claimed.
- 33 frontend tests passed; TypeScript/Vite build and shared schema check passed.
- Browser with isolated SQLite and rules-only services on ports 8791/5391:
  no phone field/option; no vehicle card in the equipment editor; missing seats
  and confirmation appear in transport. Adding a different-seat group produced
  a total of three vehicles, removing it restored two. Explicit saving and a
  newly confirmed request retained the remaining one-vehicle/five-seat record.
  Planning with no charged_phone inventory completed, estimated AUD 251, passed
  safety and displayed ready-to-save. The equipment tab contains no phone item.
  No browser console errors were recorded.
- Evidence: `evidence/a41-transport-fields.jpg` and
  `evidence/a41-ready-without-phone.jpg`.

No campus inference calls, user database changes, personal configuration changes
or sealed-data edits. Restart the backend for the new rules. Existing confirmed
requests still pin their old profile; save the updated profile and confirm a new
request to use the consolidated transport details.
