# UI improvements history — evalstone-web

Read at the start of any UI session. Standing rules (from `docs/FRONTEND.md` §9):

- **Sidebar**: expanded (icon + label) and collapsed (icon only + tooltip) modes; state in
  `localStorage` (`evalstone.sidebar.collapsed`); toggle at the bottom.
- **Page layout**: `px-[30px] py-6` on `<main>`, full width; cards constrain themselves.
- **Breadcrumbs** above every `PageHeader`: Home → List → Detail.

| Date | Asked | Applied as |
| --- | --- | --- |
| 2026-10-13 | (scaffold) | the three standing rules above |
