# MAPVIS

Archived. The current version is [MAPVIS](https://github.com/ashwath-polali/MAPVIS).

A browser tool for making 2D game maps out of a single painted image. You draw the walkable ground
onto the picture by hand at native resolution, mark elevation and things that stand in front of you,
walk it to check, and export a bundle a game engine loads.

Built for the Algorithmic Thinking Club at Bonney Lake High School.

## What is here

- `src/` the editor, React and TypeScript
- `server/` a small Node API the dev server mounts
- `archive/` an earlier approach that generated maps in 3D, kept for reference

## Running it

```
npm install
npm run dev
```

Port 5273. Drop a PNG onto the canvas to start.

## Why it stopped

The map problem was solved by hand-drawing masks over one whole painting rather than assembling maps
from parts. Hand-drawn masks measured 0.69 pixels of mean boundary error against 4.18 for derived
ones, so the correction turned out to be the deliverable. That finding is what the next version was
built around.
