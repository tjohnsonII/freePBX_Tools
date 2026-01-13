# Contributing to the Phone Config Generator Web App

Thank you for your interest in contributing! This project is modular, TypeScript-first, and designed for easy collaboration.

## Project Structure

```
src/
  components/         # Reusable UI (InfoIcon, EditableTable, etc.)
  tabs/               # Each main tab as a component (ExpansionModuleTab, PhoneConfigTab, etc.)
  templates/          # Static config templates (mikrotik, switch, etc.)
  types/              # TypeScript types/interfaces
  utils/              # Shared logic (CSV, config generation, etc.)
  constants/          # Shared constants (icons, tooltips, etc.)
  App.tsx             # Main app, handles layout and tab switching
  main.tsx            # Entry point
```

## How to Add or Update Features

- **Add a new tab:**
  1. Create a new file in `src/tabs/` (e.g., `NewFeatureTab.tsx`).
  2. Implement your feature as a React component.
  3. Import and add it to the tab navigation in `App.tsx`.

- **Add shared UI:**
  - Place reusable components in `src/components/`.

- **Add config templates:**
  - Place static templates in `src/templates/`.

- **Add shared logic:**
  - Place utility functions in `src/utils/`.

- **Add or update types:**
  - Place TypeScript interfaces/types in `src/types/`.

- **Add shared constants:**
  - Place icons, tooltips, and other constants in `src/constants/`.

## Code Style

- Use TypeScript and React best practices.
- Use functional components and hooks.
- Keep components small and focused.
- Use Prettier and ESLint for formatting and linting.
- Add comments for complex logic.

## Submitting Changes

1. Fork the repo and create a new branch.
2. Make your changes.
3. Run `npm run lint` and `npm run format` to ensure code quality.
4. Submit a pull request with a clear description.

## Questions?
Open an issue or ask in the project discussions!
