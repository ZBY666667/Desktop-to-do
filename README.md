# Desktop Todo Overlay

A lightweight desktop todo application built with pure Python and Tkinter.

It provides:

* A clean todo editor window
* A transparent floating desktop overlay
* Automatic local data persistence
* Task reminders
* Search and filtering
* Priority management
* Customizable overlay fonts and colors

No third-party dependencies required.

---

# Features

## Desktop Floating Overlay

* Transparent text overlay
* Always-on-top mode
* Draggable overlay
* Lock/unlock interaction
* Double-click to open editor
* Custom font, size, and color

## Todo Editor

* Add / edit / delete tasks
* Priority levels
* Due dates
* Search and filters
* Auto-save
* Reminder notifications

## Pure Standard Library

Built entirely with Python standard libraries:

* tkinter
* json
* dataclasses
* datetime
* pathlib

No external packages needed.

---

# Screenshots

> Recommended:
>
> Add screenshots here:
>
> * Main editor window
> * Desktop overlay
> * Custom font/color examples

---

# Demo

A short GIF demo is highly recommended.

Example workflow:

```text id="84u30v"
Create task → Desktop overlay updates instantly
```

---

# Requirements

* Python 3.10+
* Windows recommended

(The transparent overlay works best on Windows.)

---

# Run

## Clone the repository

```bash id="bz5x0z"
git clone https://github.com/yourname/desktop-todo-overlay.git
cd desktop-todo-overlay
```

## Start the application

```bash id="vhz9fx"
python desktop_todo.py
```

---

# Data Storage

All tasks and overlay settings are automatically saved to:

```text id="6k6cd3"
desktop_todo_data.json
```

This includes:

* Tasks
* Window position
* Overlay visibility
* Font settings
* Overlay lock state

---

# Supported Time Formats

Examples:

```text id="w2k3h4"
2026-05-28 18:30
2026/05/28
05-28 18:30
18:30
```

---

# Project Structure

```text id="p74g1m"
desktop_todo.py
desktop_todo_data.json
```

Core classes:

| Class               | Purpose                     |
| ------------------- | --------------------------- |
| Task                | Task data model             |
| ScrollFrame         | Scrollable container        |
| FloatingTodoOverlay | Transparent desktop overlay |
| DesktopTodoApp      | Main application controller |

---

# Technical Highlights

* Tkinter transparent overlay window
* Color-key transparency technique
* State-driven UI refresh
* Automatic JSON persistence
* Borderless floating desktop widget
* Dynamic font and color customization

---

# Future Plans

Possible future improvements:

* System tray support
* Markdown notes
* Task categories/tags
* Cloud sync
* Click-through overlay
* Themes
* Multi-monitor support

---

# License

MIT License

---

# Why This Project?

Most desktop todo tools are either:

* Too heavy
* Electron-based
* Require installation
* Or clutter the desktop

This project aims to provide a:

* Lightweight
* Minimal
* Always-visible
* Zero-dependency

desktop reminder experience.

---

# Contributing

Pull requests and suggestions are welcome.

Feel free to fork the project and improve it.

---

# Author

If you find this project useful, consider giving it a ⭐ on GitHub.
