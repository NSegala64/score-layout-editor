# Score Layout Editor

This tool automates the process of identifying systems of staves in sheet music in order to change its layout.
Possible use cases include generating sheet music videos, changing the aspect ratio of sheet music, or providing a preview of the next page at the bottom of the current page[cite: 4].

## Features

1. **Detect & Tune:** Analyzes sheet music, detects systems, and fits bounding boxes around them automatically with tunable parameters.
2. **Visual Editor:** A graphical interface to inspect bounding boxes, adjust their dimensions, and correct detection errors.
3. **Export & Render:** Re-compiles the document into a new PDF with dynamic gap calculations and custom aspect ratios.

## Installation & Launch

You do not need to manually configure virtual environments. Ensure you have [Python](https://www.python.org/downloads/) installed on your system. **If you are on Windows, you must check the box "Add Python to PATH" during the Python installation.**

### Windows
1. Download or clone this repository.
2. Double-click the `Run_Windows.bat` file.
3. The script will automatically build the virtual environment, install dependencies from `requirements.txt`, and launch the graphical editor. Subsequent launches will skip the installation and launch instantly.

### macOS & Linux
1. Download or clone this repository.
2. Open your terminal, navigate to the folder, and grant execution permissions to the script:
   ```bash
   chmod +x Run_Mac.command