# score-layout-editor

This code is an attempt to automate the process of identifying systems of staves in sheet music in order to change the layout of it.
Possible use cases : sheet music videos, changing the aspect ratio of sheet music, providing a preview of the next page at the bottom of the current page (current use).

This set of Python scripts does the following :
1. Detect the systems in sheet music and fit bounding boxes around them. Stores the coordinates of the boxes in a .json file.
2. Using a graphical interface, inspect the bounding boxes and change their dimensions if needed. Saves the changes to the .json file.
3. Render a new pdf file of the sheet music with a new layout, by changing pasting the systems using the coordinates in the .json file.

## Current usage :

Recommended use of a virtual environment to install the python packages that are missing

TODO : requirements file to automatically install dependencies
 
1. Detect the systems
`python music_layout_editor.py detect sheet_music.pdf layout.json`
2. Edit to correct mistakes 
`python visual_editor.py sheet_music.pdf layout.json`
3. Render the new file
`python music_layout_editor render sheet_music.pdf layout.json`

TODO all steps : make the whole process graphical

TODO step 3 : provide more options for the final layout (one system per page, many systems per page, ascribe a fixed aspect ratio (already possible I think)) etc

TODO step 1 : check the robustness of the process for scans of real scores. Right now only tested on a clean typesetpdf edition.

TODO step 2 : add more convenient shortcuts and ideas to the visual editor


NB : vibe coded in a hurry. Lots of cleaning up to do probably.
