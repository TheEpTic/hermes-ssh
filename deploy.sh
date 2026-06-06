#!/usr/bin/env bash
# deploy.sh — symlink nexus-plugins into ~/.hermes/plugins/
#
# Usage:
#   ./deploy.sh              # deploy all plugins (except _template)
#   ./deploy.sh ssh-tools    # deploy specific plugin(s)
#   ./deploy.sh --clean      # remove all symlinks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_PLUGINS="${HERMES_PLUGINS:-$HOME/.hermes/plugins}"
CLEAN=false
TARGETS=()

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        --help|-h)
            echo "Usage: $0 [--clean] [plugin-name ...]"
            echo "  No args    Deploy all plugins (skip _template)"
            echo "  plugin     Deploy specific plugin(s)"
            echo "  --clean    Remove all nexus-plugins symlinks"
            exit 0
            ;;
        *) TARGETS+=("$arg") ;;
    esac
done

mkdir -p "$HERMES_PLUGINS"

if $CLEAN; then
    echo "Cleaning nexus-plugin symlinks from $HERMES_PLUGINS ..."
    for link in "$HERMES_PLUGINS"/*; do
        if [ -L "$link" ] && readlink "$link" | grep -q "$SCRIPT_DIR"; then
            rm "$link"
            echo "  removed: $(basename "$link")"
        fi
    done
    echo "Done."
    exit 0
fi

# If no targets specified, deploy everything except _template
if [ ${#TARGETS[@]} -eq 0 ]; then
    for dir in "$SCRIPT_DIR"/*/; do
        name="$(basename "$dir")"
        [[ "$name" == _template ]] && continue
        [[ -f "$dir/plugin.yaml" ]] && TARGETS+=("$name")
    done
fi

for name in "${TARGETS[@]}"; do
    src="$SCRIPT_DIR/$name"
    dst="$HERMES_PLUGINS/$name"

    if [ ! -f "$src/plugin.yaml" ]; then
        echo "SKIP: $name (no plugin.yaml found)"
        continue
    fi

    if [ -L "$dst" ]; then
        rm "$dst"
    elif [ -d "$dst" ]; then
        echo "SKIP: $name (directory exists at $dst, not a symlink — not removing)"
        continue
    fi

    ln -s "$src" "$dst"
    echo "deployed: $name -> $src"
done

echo "Done. Restart Hermes (/reset or gateway restart) to load plugins."
