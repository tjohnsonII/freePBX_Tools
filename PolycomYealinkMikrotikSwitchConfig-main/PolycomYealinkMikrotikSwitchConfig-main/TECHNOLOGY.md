# Technology Overview

## Tech Stack

- **React** (with functional components and hooks): UI framework for building interactive, component-based user interfaces.
- **TypeScript**: Provides static typing for safer, more maintainable code.
- **Vite**: Fast development server and build tool for modern web apps.
- **PapaParse**: Library for CSV import/export functionality.
- **react-icons**: Icon library for consistent, modern UI icons.
- **CSS Modules / App.css**: For scoped and global styling.

## Project Structure

- `src/App.tsx`: Main app component, handles tab navigation and layout.
- `src/tabs/`: Each major feature/tab is a separate React component (e.g., ExpansionModuleTab, PhoneConfigTab).
- `src/components/`: Shared UI components (e.g., InfoIcon, EditableTable).
- `src/templates/`: Static config templates for Mikrotik, Switch, etc.
- `src/types/`: TypeScript interfaces and types for shared data structures.
- `src/utils/`: Shared utility functions (e.g., CSV helpers, config generators).
- `src/constants/`: Shared constants (icons, tooltips, etc.).

## How the App Works

- The app uses a **tabbed interface** to separate configuration generators for different device types.
- Each tab/component manages its own state and logic, making the codebase modular and easy to extend.
- **Dynamic forms** and **editable tables** allow users to input data, generate configuration code, and import/export CSV files for bulk operations.
- **Graphical previews** (for expansion modules) provide a visual representation of key layouts, with tooltips and color coding for user guidance.
- All configuration logic is written in TypeScript for type safety and maintainability.

## Adding New Features

- Add a new tab/component in `src/tabs/` for each major feature.
- Place reusable UI in `src/components/`.
- Add shared logic to `src/utils/` and constants to `src/constants/`.
- Update `App.tsx` to include new tabs in the navigation.

## Why This Stack?
- **React + TypeScript**: Modern, scalable, and widely adopted for web apps.
- **Vite**: Lightning-fast dev/build experience.
- **Component modularity**: Makes it easy for multiple developers to contribute and maintain.
- **CSV and template support**: Enables bulk operations and easy integration with other systems.

For more, see the main `README.md` and `CONTRIBUTING.md` files.
