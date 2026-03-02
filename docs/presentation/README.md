# Presentation

Browser presentation assets for Azazel-Gadget.

## Files

- `index.html`: slide player
- `ja/`: Japanese slides (`01.html` to `18.html`)
- `en/`: English slides (`01.html` to `18.html`)
- `images/`: image assets used by slides

## Run locally

Use any static file server from repository root:

```bash
cd /path/to/Azazel-Gadget
python3 -m http.server 8080
```

Open:

- `http://localhost:8080/docs/presentation/index.html`

## Controls

- `ArrowRight`/`PageDown`/`Space`: next slide
- `ArrowLeft`/`PageUp`/`Backspace`: previous slide
- `F`: fullscreen
- `H`: toggle HUD
