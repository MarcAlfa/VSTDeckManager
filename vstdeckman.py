"""VSTDeckManager - Entry point."""
import sys
from pathlib import Path

# Assicura che src/ sia nel path
sys.path.insert(0, str(Path(__file__).parent))

from src.gui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
