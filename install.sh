#!/bin/bash
# DigitalCrate installer for Macs with Apple Silicon.
#
#   curl -fsSL https://raw.githubusercontent.com/jaredhuling/DigitalCrate/main/install.sh | bash
#
# or, from a clone:  ./install.sh
#
# It installs ffmpeg and rubberband (with Homebrew), uv (Python tooling), DigitalCrate itself in ~/DigitalCrate
# (or the clone you run it from), and DigitalCrate.app in ~/Applications. Run it again any time to update.
# Nothing outside those places is changed; your music is only ever read.
set -euo pipefail

REPO_URL="${DIGITALCRATE_REPO:-https://github.com/jaredhuling/DigitalCrate.git}"
APP_DIR="${DIGITALCRATE_APP_DIR:-$HOME/Applications}"
bold() { printf "\n\033[1m%s\033[0m\n" "$*"; }
die() { printf "\n\033[31m%s\033[0m\n" "$*" >&2; exit 1; }
ask() { local a; read -r -p "$1 [Y/n] " a 2>/dev/null < /dev/tty || a=n; [[ -z "$a" || "$a" =~ ^[Yy] ]]; }

[[ "$(uname)" == Darwin && "$(uname -m)" == arm64 ]] || die "DigitalCrate needs a Mac with Apple Silicon (M1 or later)."

# run from inside a clone: use it (and don't pull: it may be your working copy)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$HERE" && -f "$HERE/pyproject.toml" ]] && grep -q '^name = "digitalcrate"' "$HERE/pyproject.toml"; then
  DIR="$HERE"; FROM_CLONE=1
else
  DIR="${DIGITALCRATE_DIR:-$HOME/DigitalCrate}"; FROM_CLONE=0
fi

bold "1/5  Homebrew"
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [[ -x $b ]] && eval "$($b shellenv)" && break; done
if ! command -v brew >/dev/null; then
  echo "DigitalCrate uses Homebrew (https://brew.sh) to install ffmpeg and rubberband."
  ask "Install Homebrew now? It will ask for your Mac password." || die "Install Homebrew, then run this again."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" < /dev/tty
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo "ok: $(brew --version | head -1)"

bold "2/5  ffmpeg and rubberband (audio decoding and time-stretching)"
for f in ffmpeg rubberband; do
  if brew list --versions "$f" >/dev/null; then echo "ok: $f"; else brew install "$f"; fi
done

bold "3/5  uv (installs Python and the packages)"
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
echo "ok: $(uv --version)"

bold "4/5  DigitalCrate in $DIR"
if [[ $FROM_CLONE == 0 ]]; then
  if [[ -d "$DIR/.git" ]]; then git -C "$DIR" pull --ff-only || echo "(couldn't update: local changes? keeping your copy)"
  else git clone --depth 1 "$REPO_URL" "$DIR"; fi
fi
cd "$DIR"
[[ -x .venv/bin/python ]] || uv venv --python 3.11 .venv
echo "installing packages (a few GB the first time; a few minutes)…"
uv pip install --quiet --python .venv/bin/python --no-deps -r requirements.lock
uv pip install --quiet --python .venv/bin/python --no-deps -e .

bold "5/5  DigitalCrate.app"
.venv/bin/python -m digitalcrate app --dest "$APP_DIR"

bold "Done."
echo "Open DigitalCrate from Applications, Launchpad or Spotlight. The first time, it asks where your music is."
echo "To uninstall: delete $DIR and $APP_DIR/DigitalCrate.app (your sample library stays where you put it)."
if ask "Open it now?"; then open "$APP_DIR/DigitalCrate.app"; fi
