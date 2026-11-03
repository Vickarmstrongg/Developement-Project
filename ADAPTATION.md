# Adaptation Document: Byte & Bite

### Developer group: The Final Commit (David, Matthew, Victoria, Nicole)

### Client group: Group 4 (product owners of Byte & Bite)

### Case: BoschCard premium information service for student-oriented cafés, coffee shops and quick-service food businesses in Stellenbosch

This document records how we adapted the requirements in Group 4's concept note during the six weekly client sessions (22 September to 27 October 2026). For each part of the system it explains what the concept note asked for, what the client clarified or changed in the sessions, and how we adapted the system as a result. It also lists the constraints that shaped our decisions and what was left out or deferred. Setup and running instructions are in the README.


## 1. How we handled requirements

We worked in weekly agile sprints, with one sprint for each client session. Before each session we prepared an agenda and a list of questions, and afterwards we recorded the decisions and open questions in our minutes. Where the concept note was silent or ambiguous we asked the client rather than assuming. Where a client request conflicted with the brief, for example the provided data model, we explained the constraint, proposed an alternative and let the client choose.

To manage scope, we asked the client at Session 1 which two features mattered most if time ran short. They named Rush Hour Radar and Demand Forecast as non-negotiable, so we built these first as our minimum viable product. Fair Comparison Score and the Honest Results Checker followed.

Three constraints shaped most of our adaptations: the provided ERD (Student, Vendor, Vendor_Type and Transaction), the brief's requirements on student privacy and on not presenting correlation as causation, and the six-week timeline.


## 2. Adaptations by feature

### 2.1 Rush Hour Radar

The concept note asked for a view of recurring peak and quiet trading periods, with promotion suggestions for quiet periods. At Session 1 the client clarified that the analysis should work by day of the week and hour, show both busy and quiet periods, and use visual charts and heat maps. They also said recommendations should be generated automatically once a threshold is met, with the manager deciding whether to act on them, and that managers should not enter promotions themselves. At Session 2 they added that suggested discounts should be based on how past discounts performed.

The concept note did not say how busy and quiet should be defined, so at Session 2 we agreed four levels: quiet, moderate, busy and very busy. These are based on a four-week baseline for the same day and hour, using percentile cut-offs at 25, 50 and 75. The levels are shown as labels and not as percentages. The client also asked for a geographical map of Stellenbosch divided into zones, filterable by vendor type and operational size, so we built a zone-based map in which zones group vendors together and no single business is exposed. After Session 3 feedback on the map (larger dots and better scrolling), the client asked at Session 4 for a more readable layout, so we rebuilt the page around a sortable, filterable table with pagination and a fixed sidebar. At Session 5 they asked for recommendations in a searchable table with a "last updated" time, for the dismiss option on auto-generated items to be removed, and for managers and staff to see only their own business and recommendations while admins see everything. These role limits are enforced on the server.

### 2.2 Fair Comparison Score

The concept note asked for comparison with aggregated groups of similar businesses. At Session 1 the client specified that peer groups should be based on vendor type and on size, not on type alone, and that the result should be an above or below average label, with a percentile screen. Because size is not part of the provided ERD, we proposed at Session 2 that it be derived from transaction volume (small, medium or large), and the client agreed. This means size is calculated when the comparison is made and no new column was added to the data model.

To protect competitors, the client set a minimum peer group size, and at Session 3 asked that only aggregated statistics be shown and never the values of individual businesses. When a peer group is too small, the page shows a short "not enough data yet" message instead of a comparison. Later sessions added a filter by day (Session 3), a bar graph for a single day (Session 4), and extra context and specific periods on the page (Session 5). At Session 2 the client also decided that Fair Comparison should be hidden from the staff role entirely, and we block it on the server as well as hiding it in the interface.

### 2.3 Honest Results Checker

The concept note asked for context warnings when events overlap with a change in demand. At Session 1 the client defined which events matter: exams, recess, public holidays, sport, graduation, payday and other general student events, but not events that only affect a small group. They said that flags and pop-ups would be annoying, and at Session 2 settled on two mechanisms together: a notification bell with a list of messages, and contextual details shown when hovering over charts. At Session 3 they set a trigger of a 30% increase or decrease against the normal baseline, and asked that notifications can be pinned and cleared.

Throughout, the client insisted that correlation is never presented as causation, so every message states only that events coincided with a change. At Session 5 we changed how the information is displayed and removed raw formatting characters such as curly brackets.

The calendar of events needed a particular adaptation. Because the brief limits the data model, we first proposed keeping the calendar as a separate uploadable list and not as a database table. The client then asked for proper database tables, with an Admin able to create, update and delete events, so we store events in their own table, separate from the four required entities. Admins choose an event type from a list and enter a name and dates. At Sessions 4 and 5 the client asked for a calendar view alongside the list, and for only external events to be tracked.

### 2.4 Demand Forecast

The concept note asked for an estimate of future demand from historical patterns and context. At Session 1 the client set a weekly horizon, ruled out machine learning, and asked for one graph with three lines: transactions, customers and revenue. They considered adding a line for average spend per student, but this stayed undecided, so the graph was kept at three lines.

At Session 2 the client decided that staff should see transactions and customers but not revenue. The revenue field is removed on the server before the response is sent, so staff cannot retrieve it by inspecting network requests. At Sessions 4 and 5 the client asked for bigger card headings, a searchable vendor selector (with a "Vendor" label and delayed search), a faint grid on the chart and the PDF export, weekday names on the dashboard widget, and a recommendations view with a table and a suggested discount. In the final session they asked for two decimals on all figures, thousands separators, consistent date formats, separate day and date columns, and a filter to switch between transaction count and revenue.

### 2.5 Dashboard, reports and notifications

At Sessions 3 and 4 the client asked for the landing page to be a quick overview with widgets that link to each feature, and for a consistent look across pages: uniform cards, equal spacing, and filters and tabs in the same place on every page. Later feedback asked for the date bar to be removed, for the day of the week to appear on the trend chart, and for the dashboard to explain why a busiest period cannot be shown when that happens.

For reports, the client asked at Session 4 that every main page can export a report, that staff may export but must not see revenue, that past reports can be accessed again, and that managers can see who exported what and when. We built per-page PDF export and a Reports page that logs each export. For notifications, the client asked for a stacked preview when there is more than one, so we built a notification history page and made the bell behave the same way on every page.

### 2.6 Users, roles and login

The concept note did not describe users, so we elicited this at Session 1. The client asked for three roles: an Admin who invites users, a Manager, and a read-only Staff role with a simple, shift-relevant view. There is no self-registration, access is by invitation only, and one user can be linked to several businesses through a drop-down switcher. At Session 2 the client confirmed that only the Admin can edit vendor details and that managers send change requests to the Admin. At Session 3 the client specified that invitation links expire after 24 hours, and at Session 5 that users can reset their own password through an email link, with the Admin still able to reset passwords and an audit log of who changed them. During development we use a local mail tool so we can test these emails.


## 3. Privacy and safeguard adaptations

Privacy was a first-class requirement, so these decisions were made together with the client. No student ID, name or address is shown, and student IDs are randomised in the data pipeline. Locations are shown at zone level and not as exact addresses or coordinates. When a result would rest on a single student, it is merged into another group or hidden. Peer comparisons show aggregated statistics only and never reveal a competitor's identity or figures. Role restrictions are checked on the server and not only hidden in the interface.

The minimum group size for students needed particular care. The client first asked for at least 10 students in a time slot, but when we tested this against the data, most three-hour meal slots had only three to nine students, so nearly everything was hidden. At Session 3 we presented three options: lower the threshold to 5, lower it to 3, or keep 10 and count students over a longer history. We recommended the third because it left the client's own number untouched. The client chose to lower the threshold to 5.


## 4. Data adaptations

The client's synthetic data arrived later than planned and was later replaced with a larger dataset, with roughly double the students and vendors and a structure closer to the ERD. We re-checked the system against the new data. Vendor types were also widened beyond two, to Restaurants, Cafés and Bakeries. Records created from the earlier dataset, such as the report export log, are cleared when the new data is loaded.



## 5. Out of scope, deferred or left open

Machine-learning forecasting was left out at the client's request. The line for average spend per student could not be decided and was not built. The client raised, but did not settle, whether BoschCard itself should have a separate super-user role, so this was not built. Forecast accuracy targets were deferred. Taking orders, payments, delivery dispatch, menu or inventory management, and automatic changes to prices or staffing were outside the concept note's scope.



## 6. Performance adaptation

After Session 5 the team agreed to reduce loading times. We added skeleton loaders for the first load, caching of repeated calculations on the server, and a short memory cache in the browser so that revisited pages appear immediately and refresh quietly in the background.


## 7. Technology choices

No stack was mandated and the client accepted ours. We used PostgreSQL (hosted on Neon) for persistence, a Python and FastAPI backend, and a React frontend. The written justification for these choices is kept with the project documentation.
