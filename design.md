# UI/UX Design & Frontend Structure

## Design Philosophy
- **Minimalist & Clean:** The UI should focus on core functionalities—uploading, viewing, sharing, and managing files without unnecessary clutter.
- **Responsive:** The layout must adapt seamlessly across desktop, tablet, and mobile devices.
- **Feedback-Driven:** Provide clear visual feedback for user actions (e.g., upload progress bars, QR code scanning instructions, share link generation).

## Frontend Structure
The frontend relies on Vanilla JavaScript, HTML, and CSS, avoiding heavy frameworks to keep the payload light and execution fast.

### Directory Layout
- `/frontend`
  - `/css`: Stylesheets (global styles, dashboard specific styles).
  - `/js`: Logic and interactivity.
    - `api.js`: Centralized fetch wrapper (`apiFetch`).
    - `config.js`: Environment variables (API Base URL).
    - `dashboard.js`, `login.js`, `register.js`, `setup_telegram.js`, `share.js`: Page-specific logic.
  - `*.html`: View templates.

### Styling Guidelines
- **CSS Variables:** Use CSS variables for consistent theming (colors, typography, spacing).
- **Flexbox/Grid:** Utilize modern CSS layout modules for structuring components.
- **Modularity:** Keep CSS files focused on specific components or pages where possible.

### Interaction Patterns
- **API Calls:** All external data fetching must go through `apiFetch`.
- **Telegram Authentication (QR Login):** The `setup_telegram.js` periodically polls the backend to check if the user has successfully scanned the QR code via their Telegram app, offering a seamless login experience.
- **File Sharing:** Generates unique shareable URLs. Visiting a shared URL triggers `share.js` which fetches file metadata and offers a "Save to my Cloud" feature.
- **State Management:** Simple state is managed via `localStorage` (e.g., auth tokens). More complex state is derived directly from the DOM or encapsulated within module-level variables in specific JS files.
- **Routing:** Navigation is handled via standard HTML links, relying on `vercel.json` to ensure correct file serving in the production environment.
