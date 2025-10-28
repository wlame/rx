#!/bin/bash
# Build script for RX binary

set -e

echo "🔨 Building RX binary..."
echo ""

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed"
    echo "Please install uv: https://docs.astral.sh/uv/"
    exit 1
fi

# Install build dependencies
echo "📦 Installing build dependencies..."
uv sync --group build

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ 2>/dev/null || true

# Run PyInstaller with spec file
echo "🏗️  Running PyInstaller..."
uv run pyinstaller rx.spec --noconfirm

# Check if build was successful
if [ -f "dist/rx" ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "Binary location: dist/rx"
    echo "Binary size: $(du -h dist/rx | cut -f1)"
    echo ""
    echo "To run the binary:"
    echo "  ./dist/rx /path/to/file \"pattern\"    # Search mode (default)"
    echo "  ./dist/rx check \"(a+)+\"              # Check regex complexity"
    echo "  ./dist/rx serve --port 8000           # Start web server"
    echo ""
    echo "⚠️  Note: ripgrep must be installed on the system where you run this binary"
    echo ""
else
    echo ""
    echo "❌ Build failed!"
    exit 1
fi
