# CampMate Synthetic UI Content

| Message ID | Situation | Severity | User-facing English text | Recommended user action |
|---|---|---|---|---|
| UI-01 | Any prototype screen | INFO | This prototype uses synthetic demonstration data. It must not be used for real trip planning, campsite availability, or safety decisions. | Continue only for demonstration and testing. |
| UI-02 | Profile is incomplete | WARNING | Please complete the required profile fields before continuing. | Add the missing profile information. |
| UI-03 | Invalid group size | ERROR | Group size must be at least one camper. | Enter a valid group size. |
| UI-04 | Invalid date | ERROR | Please enter a valid trip start date. | Choose a valid future demo date. |
| UI-05 | Invalid date order | ERROR | The trip end date must be after the start date. | Correct the trip dates. |
| UI-06 | Missing budget | WARNING | We need a budget to compare the plan cost. | Enter your maximum budget in AUD. |
| UI-07 | Invalid budget | ERROR | Budget must be greater than zero. | Enter a valid AUD budget. |
| UI-08 | Request unconfirmed | INFO | Your request is waiting for your confirmation. | Review the details and confirm the request. |
| UI-09 | Unsupported region | ERROR | This prototype only supports CampMate Demo Region. | Choose CampMate Demo Region. |
| UI-10 | No campsite match | WARNING | No demo campsite matches all required conditions. | Relax a preference or revise the request. |
| UI-11 | Campsite recommendation | INFO | This campsite is recommended because it matches your confirmed demo constraints. | Review the recommendation reasons. |
| UI-12 | Tent missing | ERROR | Your group does not have enough tent capacity for this plan. | Add, hire, or borrow suitable tent capacity. |
| UI-13 | Sleeping bag missing | ERROR | One or more campers need a sleeping bag. | Add or hire sleeping bags before continuing. |
| UI-14 | Over budget | WARNING | The estimated demo cost exceeds your stated budget. | Reduce cost, change dates, or increase the budget. |
| UI-15 | Cost mismatch | ERROR | The estimated total does not match its cost breakdown. | Recalculate the plan before review. |
| UI-16 | Safety data missing | WARNING | Some synthetic safety data is missing. The plan cannot be described as safe. | Send the plan for Human Review. |
| UI-17 | Safety data stale | WARNING | Some synthetic safety data is stale. | Request updated demo data and send for review. |
| UI-18 | Conflicting information | WARNING | Synthetic safety information is conflicting. | Do not proceed until Human Review is complete. |
| UI-19 | Road closed | ERROR | Road access is marked closed in this demo scenario. | Choose another campsite or date. |
| UI-20 | Campsite closed | ERROR | This demo campsite is marked closed. | Choose another campsite. |
| UI-21 | No-fire restriction | WARNING | Campfires are not permitted for this demo campsite. | Remove the campfire activity and use a fire-free meal plan. |
| UI-22 | Human Review needed | INFO | This plan is waiting for Human Founder review. | Wait for an approval, rejection, or revision request. |
| UI-23 | Founder revision | WARNING | The Human Founder requested changes to this plan. | Create a new plan version and address the feedback. |
| UI-24 | Founder rejection | ERROR | The Human Founder rejected this plan. | Create a new request or revise the plan. |
| UI-25 | Old version approval | ERROR | An older plan version cannot be approved after a newer version exists. | Review and approve the latest version only. |
| UI-26 | Unauthorised operation | ERROR | You are not authorised to approve this plan. | Ask a Human Founder to review it. |
| UI-27 | Final save failure | ERROR | The final plan could not be saved. | Try saving again after the issue is resolved. |
| UI-28 | Final plan saved | SUCCESS | Your final demo plan has been saved. | Review the final plan summary. |
| UI-29 | Agent unavailable | ERROR | An AI Agent service is unavailable in this prototype. | Try again later or send the plan for Human Review. |
| UI-30 | Plan blocked | ERROR | This plan has a mandatory blocker and cannot be finalised. | Select another option and create a new plan version. |
